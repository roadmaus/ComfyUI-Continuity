"""Which family renders a piece is a field of the piece, and everything reads it.

Written when LTX 2.5 arrived. `manifest.js` exported `VIDEO` — *the* family
that produces video — and `state.js` and `canvas.js` bound to it at module load.
With a second video family that binding is wrong by construction, so the piece
gained a `family` field and the readers gained accessors that take one.

The awkward part is that phase 1 lands while there is still exactly one family,
which makes "the controls read the piece's family" unprovable against this
install's catalog: every answer is H3's whether it was looked up or hardcoded.
So the frontend half runs twice — once against the real catalog, where nothing
may have changed, and once against a **probe** catalog carrying a second video
family whose every number differs from H3's. A reader still bound to a module
constant answers H3 for the probe piece and is caught here.

The probe is H3's own manifest with its ids and numbers rewritten, rather than a
hand-written one: a fixture invented here would drift from the manifest contract
the moment `check()` grew a key, and what is being tested is the binding, not
the shape.

What must hold on both sides:

- absent `family` means H3, permanently — every workflow saved before the field
  existed is one, and opening one must not change what it renders with;
- an unknown id means H3 too, on `compile.piece_family`'s terms: a blob naming a
  family this install does not have is a piece to draw, not a queue to refuse;
- a piece on the default family serialises to the bytes it always did, which is
  what makes the field free to add;
- switching families rebuilds everything keyed by the old family's vocabulary
  and keeps everything that is the user's writing.

    python3 tests/test_family_select.py

Skips itself if node is not installed.
"""

import copy
import json

import layout

layout.skip_without_node()

from harness import FAILURES, check, passed

_pkg = layout.load("canvas", "registry", "manifest", "contextir", "subjects",
                   "compile", "ltx25_declare")
LTX25 = _pkg.ltx25_declare.RULES
compiler, registry = _pkg.compile, _pkg.registry
canvas, manifest = _pkg.canvas, _pkg.manifest
catalog = manifest.catalog()

STATE = layout.js("state.js")

# ---- the registry and the served catalog ------------------------------------

check("h3 is the default video family", registry.DEFAULT_VIDEO, "h3")
check("the video families are the ones that produce video",
      registry.video_families(),
      tuple(f for f in registry.FAMILIES if "video" in registry.PRODUCES[f]))
check("the catalog serves the list", catalog["video_families"],
      list(registry.video_families()))
check("the catalog serves the default", catalog["default_video_family"],
      registry.DEFAULT_VIDEO)

# ---- compile.piece_family ----------------------------------------------------

CASES = [
    ("a fresh node", {}, "h3"),
    ("a piece that names none", {"version": 2, "segments": []}, "h3"),
    ("a v1 creator blob", {"version": 1, "prompt": "a street"}, "h3"),
    ("a piece that names the default", {"version": 2, "segments": [], "family": "h3"}, "h3"),
    # Not a refusal: a hand-edit, or a workflow off a machine with a family this
    # install has not got, still has a video in it.
    # Deliberately an id no registry row answers to, and it must stay one: the
    # first draft of this case said "ltx25", which stopped testing anything the
    # day LTX 2.5 was registered.
    ("a piece naming a family that is not installed",
     {"version": 2, "segments": [], "family": "not_a_family"}, "h3"),
    ("a piece whose family is not even a string",
     {"version": 2, "segments": [], "family": 7}, "h3"),
    ("something that is not a blob at all", "nonsense", "h3"),
]
for label, blob, want in CASES:
    check(f"piece_family: {label}", compiler.piece_family(blob), want)

check("family is a piece field, so a v1 lift would carry it up",
      "family" in compiler.PIECE_FIELDS, True)

# ---- the probe catalog -------------------------------------------------------
#
# H3's manifest with everything a control could read off it changed: the slot
# ids, the routes, the canvas grid, the turbo row. Registered second, so the
# default stays H3 and the piece has to *say* it is on the probe.

probe = copy.deepcopy(catalog["families"][0])
probe.update({"id": "probe", "label": "Probe", "description": "The second family."})
probe["weights"] = [
    {**slot, "id": f"p_{slot['id']}"} for slot in probe["weights"]
]
probe["routes"] = {"options": ["auto", "p_fl2va", "p_ref2va"], "default": "p_ref2va",
                   "reference": "p_ref2va", "plain": "p_fl2va", "timeline": "p_ref2va"}
probe["canvas"] = {**probe["canvas"],
                   "multiple": 16, "fps": {"value": 25, "fixed": False},
                   "min_short_edge": 256, "max_short_edge": 1024,
                   "native_short_edge": 512,
                   "frames": {**probe["canvas"]["frames"], "step": 8, "offset": 1}}
probe["capabilities"] = {**probe["capabilities"], "duration_head": True}

PROBE_CATALOG = {**catalog,
                 "families": [*catalog["families"], probe],
                 "video_families": [*catalog["video_families"], "probe"]}

# ---- the frontend, on the real catalog: nothing moved ------------------------

REAL = """
const S = await import(process.argv[1]);
const round = (blob) => JSON.parse(S.serializeTimeline(S.parseTimeline(JSON.stringify(blob))));
console.log(JSON.stringify({
  families: S.VIDEO_FAMILIES,
  fallback: S.DEFAULT_VIDEO_FAMILY,
  fresh: S.emptyTimeline().family,
  fields: S.PIECE_FIELDS,
  resolved: JSON.parse(process.argv[2]).map((blob) => S.pieceFamily(S.parseTimeline(JSON.stringify(blob)))),
  // The bytes. A piece on the default family must serialise to exactly what it
  // did before the field existed — which is what makes adding it free.
  freshBlob: round({}),
  writtenBlob: round({ version: 2, prompt: "a street", family: "h3", segments: [{ prompt: "one" }] }),
}));
"""

blobs = [blob for _, blob, _ in CASES if isinstance(blob, dict)]
real = layout.run(REAL, STATE, blobs)

check("the frontend lists the families the registry does",
      real["families"], list(registry.video_families()))
check("...and falls back where the compiler does",
      real["fallback"], registry.DEFAULT_VIDEO)
check("a fresh piece is on the default family", real["fresh"], registry.DEFAULT_VIDEO)
check("the piece fields still mirror", real["fields"], list(compiler.PIECE_FIELDS))
check("pieceFamily resolves what piece_family does",
      real["resolved"], [compiler.piece_family(blob) for blob in blobs])
check("a piece on the default family writes no family key",
      "family" in real["freshBlob"], False)
check("...written or not", "family" in real["writtenBlob"], False)
check("...and is otherwise the piece it was",
      real["writtenBlob"]["prompt"], "a street")

# ---- the frontend, on the probe catalog: the piece decides -------------------

PROBE = """
const S = await import(process.argv[1]);
const C = await import(process.argv[2]);
const piece = S.parseTimeline(JSON.stringify(JSON.parse(process.argv[3])));

// A piece switched to the probe, having been set up on the default first: a
// weights block, a turbo file, a pinned checkpoint and a LoRA aimed at one.
const switched = S.parseTimeline(JSON.stringify({
  version: 2, prompt: "a street",
  aspect: "21:9", short_edge: 2048, sample_edge: 2048,
  models: { fl2va: "fl2va.safetensors", route: "fl2va" },
  turbo: { lora: "lightx2v.safetensors", on: true },
  loras: [{ name: "grain.safetensors", strength: 0.8, modes: ["fl2va"] }],
  segments: [{ prompt: "one", checkpoint: "fl2va" }],
}));
const before = JSON.parse(JSON.stringify(switched));
const changed = S.setFamily(switched, "probe");

console.log(JSON.stringify({
  families: S.VIDEO_FAMILIES,
  fallback: S.DEFAULT_VIDEO_FAMILY,
  // Read off the piece, not off the module.
  resolved: S.pieceFamily(piece),
  slots: S.modelFields("probe"),
  routes: S.routeOptions("probe"),
  checkpoints: S.checkpointsOf("probe"),
  emptyRoute: S.emptyModels("probe").route,
  // A block stored under the other family's ids is not this family's block.
  crossed: S.parseModels({ fl2va: "fl2va.safetensors" }, "probe"),
  // The canvas rules follow the piece too — different grid, different fps.
  rules: (({ multiple, fps, fpsFixed, frameStep, frameOffset, nativeShortEdge }) =>
    ({ multiple, fps, fpsFixed, frameStep, frameOffset, nativeShortEdge }))(C.rulesFor("probe")),
  defaultRules: (({ multiple, fps, fpsFixed }) => ({ multiple, fps, fpsFixed }))(C.VIDEO_RULES),
  // A capability H3 has not got, asked of the piece rather than of an id.
  hasHead: [S.canDo(piece, "duration_head"), S.canDo({}, "duration_head")],

  changed,
  again: S.setFamily(switched, "probe"),
  switched: {
    family: switched.family,
    models: switched.models,
    turboLora: switched.turbo.lora,
    loraModes: switched.loras[0].modes,
    loraName: switched.loras[0].name,
    pinned: "checkpoint" in switched.segments[0],
    // Kept: the writing is a piece, not a checkpoint's idea of one.
    prompt: switched.prompt,
    shot: switched.segments[0].prompt,
    // Re-clamped to the probe's edges, and the aspect it has no name for.
    short_edge: switched.short_edge,
    sample_edge: switched.sample_edge,
    aspect: switched.aspect,
  },
  beforeEdge: before.short_edge,
  // The switch survives a round trip, because it is no longer the default.
  roundTrip: JSON.parse(S.serializeTimeline(switched)).family,
}));
"""

probed = layout.run(PROBE, STATE, layout.js("canvas.js"),
                    {"version": 2, "family": "probe", "segments": []},
                    catalog=PROBE_CATALOG)

check("the probe is listed alongside the registered families",
      probed["families"], [*registry.video_families(), "probe"])
check("...without becoming the default", probed["fallback"], "h3")
check("a piece on the probe resolves to it", probed["resolved"], "probe")

check("the slot ids are the probe's", probed["slots"],
      [f"p_{slot['id']}" for slot in catalog["families"][0]["weights"]])
check("so are the routes", probed["routes"], probe["routes"]["options"])
check("and the routed checkpoints", probed["checkpoints"], ["p_fl2va", "p_ref2va"])
check("an empty block routes where the probe says", probed["emptyRoute"], "p_ref2va")
check("a filename in another family's slot is not carried over",
      probed["crossed"].get("fl2va"), None)
check("...and the probe's own slot is empty", probed["crossed"]["p_fl2va"], "")

check("the canvas rules are the probe's",
      probed["rules"],
      {"multiple": 16, "fps": 25, "fpsFixed": False,
       "frameStep": 8, "frameOffset": 1, "nativeShortEdge": 512})
check("...and the default family's are untouched",
      probed["defaultRules"], {"multiple": 32, "fps": 24, "fpsFixed": True})
check("a capability is asked of the piece", probed["hasHead"], [True, False])

# ---- the frontend, on the second real family ---------------------------------
#
# The probe above proves a control reads the *piece* rather than a module
# constant, by being a family shaped so that a stale reader answers H3. This
# proves the registered second family arrives intact through the same path —
# and it is where an id-shaped assumption about H3 that the probe inherited
# (its weights are H3's slots renamed, so every one of them is required) has
# somewhere to fail.

LTX = """
const S = await import(process.argv[1]);
const C = await import(process.argv[2]);
const piece = S.parseTimeline(JSON.stringify({
  version: 2, prompt: "a street", aspect: "21:9", short_edge: 1536, sample_edge: 1024,
  models: { fl2va: "fl2va.safetensors", route: "ref2va" },
  turbo: { lora: "lightx2v.safetensors", on: true },
  segments: [{ prompt: "one", checkpoint: "fl2va" }],
}));
const changed = S.setFamily(piece, "ltx25");
const r = C.rulesFor("ltx25");
console.log(JSON.stringify({
  changed, family: piece.family,
  slots: S.modelFields("ltx25"),
  // A family with one transformer routes between nothing, and its blob says
  // nothing about a route — the NO_ROUTING fallback, not a control of one.
  checkpoints: S.checkpointsOf("ltx25"),
  routes: S.routeOptions("ltx25"),
  required: S.alwaysRequired("ltx25"),
  devices: S.deviceFields("ltx25"),
  // Carried over from the H3 setup: no filename at all, under either family's
  // slot ids. The block's own scaffolding (dtype, route, devices) is not a
  // pick and is rebuilt empty.
  leftover: [...S.modelFields("h3"), ...S.modelFields("ltx25")]
    .filter((slot) => piece.models[slot]),
  turboLora: piece.turbo.lora,
  pinned: "checkpoint" in piece.segments[0],
  rules: { multiple: r.multiple, fps: r.fps, fpsFixed: r.fpsFixed,
           step: r.frameStep, offset: r.frameOffset },
  sample_edge: piece.sample_edge,
  // The card's own reference numbers, arrived at through the served rules.
  frames: [C.framesForSeconds(1, r), C.framesForSeconds(5, r), C.framesForSeconds(20, r)],
  wxh: C.resolveCanvas(16 / 9, r.nativeShortEdge, r),
  duration: [S.canDo(piece, "duration"), S.canDo({}, "duration")],
  roundTrip: JSON.parse(S.serializeTimeline(piece)).family,
}));
"""

ltx = layout.run(LTX, STATE, layout.js("canvas.js"))
ltx_manifest = manifest.describe("ltx25")

check("switching to LTX 2.5 changes the piece", (ltx["changed"], ltx["family"]),
      (True, "ltx25"))
check("the slot ids are the family's",
      ltx["slots"], [slot["id"] for slot in ltx_manifest["weights"]])
check("nothing keyed by H3's vocabulary survives the switch",
      (ltx["leftover"], ltx["turboLora"], ltx["pinned"]), ([], "", False))
check("one transformer routes between nothing",
      (ltx["checkpoints"], ltx["routes"]), ([], ["auto"]))
# The one that had to be found: `alwaysRequired` filtered on loads-and-not-routed,
# which made both opt-in passes weights the queue would refuse without.
check("the opt-in passes are not required weights",
      ltx["required"],
      [slot["id"] for slot in ltx_manifest["weights"] if slot["required"]])
check("a device pins only where MultiGPU has a wrapper",
      ltx["devices"],
      [slot["id"] for slot in ltx_manifest["weights"] if slot["device"]])
check("the canvas rules are LTX 2.5's, off the served manifest",
      ltx["rules"],
      {"multiple": 32, "fps": 24, "fpsFixed": False, "step": 8, "offset": 1})
check("the first-pass edge re-clamps to the new native size",
      ltx["sample_edge"], LTX25.native_short_edge)
# Lightricks' own reference pipeline: 121 frames at 24 fps, sampled at 960x544.
check("the frame grid lands on the card's numbers", ltx["frames"], [25, 121, 481])
check("the native canvas is the card's stage one", ltx["wxh"], [960, 544])
check("the duration head is a capability H3 has not got",
      ltx["duration"], [True, False])
check("a piece off the default family keeps its family through a round trip",
      ltx["roundTrip"], "ltx25")

# ---- the switch --------------------------------------------------------------

check("switching reports that it switched", probed["changed"], True)
check("...and switching again does not", probed["again"], False)

switched = probed["switched"]
check("the piece is on the probe", switched["family"], "probe")
check("the weights block is the probe's, empty",
      switched["models"], {"dtype": "default", "route": "p_ref2va", "devices": {},
                           "p_fl2va": "", "p_ref2va": "", **{
                               f"p_{slot['id']}": ""
                               for slot in catalog["families"][0]["weights"]}})
check("the turbo LoRA is dropped — it was distilled against the old weights",
      switched["turboLora"], "")
check("a card's checkpoint pin is dropped", switched["pinned"], False)
check("a LoRA is retargeted rather than dropped",
      (switched["loraName"], switched["loraModes"]),
      ("grain.safetensors", ["p_fl2va", "p_ref2va"]))
check("the writing stays", (switched["prompt"], switched["shot"]), ("a street", "one"))
check("the canvas is re-clamped to the probe's ceiling, the first pass to its native",
      (probed["beforeEdge"], switched["short_edge"], switched["sample_edge"]),
      (2048, 1024, 512))
check("the aspect is one the probe lists", switched["aspect"], "21:9")
check("the switch is written to the blob", probed["roundTrip"], "probe")

# ---- the controls, taught to ask ---------------------------------------------
#
# Phase 3's other half. The accessors above existed from phase 1; what was still
# bound to the default family was the code that *calls* them — the weights
# popover, the sampler row and the LoRA manager all read a module constant. Two
# claims are worth pinning, and neither needs a DOM.
#
# First, that the constants are gone from those three files. A grep, because the
# failure mode is a reader that still compiles and quietly answers H3, and the
# only reliable evidence against it is the absence of the name.

# The reference grammar splits into two halves that are checked differently, and
# the split is the point.
#
# The **vocabulary** — the takes, the tracks, the default sizes — comes from
# `compile.py`'s own constants and is shared by construction, so it must be
# identical on every family. `state.js` still reads it off one of them.
#
# The **counts** are the family's own, and this suite used to hold them
# identical too. They are not any more: LTX 2.5 takes nothing, because a
# citation reaches its encoder as a bare `<Picture 1>` with no picture behind
# it. That is what `refCaps(piece)` exists for, and holding the counts equal
# here would be re-asserting the thing that turned out to be false.
_video = [m for m in catalog["families"] if "video" in m["produces"]]
_grammars = [m.get("reference") for m in _video]
check("every video family declares a reference grammar",
      [m["id"] for m in _video if m.get("reference") is None], [])
_shared = lambda block: {k: v for k, v in block.items() if k != "max"}   # noqa: E731
for entry in _grammars[1:]:
    check("the video families share one reference vocabulary",
          _shared(entry), _shared(_grammars[0]))

# A family that takes nothing has to say so in every count, not only in the
# total: `capacity(state, kind, piece)` reads them per kind, and a zero `files`
# beside a nine `image` would draw an enabled tool that refuses on click.
for entry, family in zip(_grammars, _video):
    caps = entry["max"]
    check(f"{family['id']}: the caps agree with each other",
          bool(caps["files"]) or not any(caps[k] for k in ("image", "video", "audio")),
          True)

# ...and the mode vocabulary is *not* shared, which is why `mode()` takes the
# piece. Each family names the payload shapes its own segment node builds.
_modes = [m.get("modes") for m in _video]
check("every video family names its modes",
      [m["id"] for m in _video if not m.get("modes")], [])
check("the mode names are the family's own, not one shared list",
      len({tuple(sorted(m.items())) for m in _modes}), len(_modes))


CONTROLS = ("models.js", "sampling.js", "loras.js", "editor.js", "timeline.js")
BOUND = ("S.MODEL_FIELDS", "S.MODEL_LABEL", "S.MODEL_HINT", "S.CHECKPOINTS",
         "S.CHECKPOINT_LABEL", "S.CHECKPOINT_WHEN", "S.DEVICE_FIELDS",
         "S.ROUTES", "S.ALWAYS_REQUIRED",
         # Phase 4's addition. The seam widths are the family's video VAE's —
         # H3's 5-frame blend reaches LTX as a single frame, silently — so a
         # control reading the module constant draws a picker whose options the
         # queue will refuse. `featherGridOf(piece)` is the one to reach for.
         "S.FEATHER_GRID")
for name in CONTROLS:
    source = open(layout.js(name), encoding="utf-8").read()
    for bound in BOUND:
        if bound in source:
            FAILURES.append(
                f"{name} still reads {bound}, which is the default family's — "
                f"take the family off the piece instead")

# Second, that the family-taking versions answer differently for two families,
# which is the whole of what "reads the piece" buys. The probe's slots are H3's
# renamed, so a reader still bound to the default answers with H3's ids and is
# caught by the *values* rather than by the shape.

CONTROLS_JS = """
const S = await import(process.argv[1]);
const both = (fn) => [fn("h3"), fn("probe")];
console.log(JSON.stringify({
  // What the weights popover draws a row for, and what it calls each row.
  fields: both(S.modelFields),
  labels: both((id) => Object.keys(S.modelLabels(id))),
  devices: both(S.deviceFields),
  // Whether it draws a route row at all, and a per-LoRA checkpoint control.
  routing: both(S.routing),
  // What it refuses a queue over, and what the pill reports as missing. The
  // probe's ids are H3's prefixed, so an empty block is missing the probe's.
  required: both((id) => S.requiredModels([], false, id)),
  missing: both((id) => S.missingModels({}, S.requiredModels([], false, id), id)),
  // What the sampler row draws, which is the manifest's control list.
  widgets: both((id) => S.widgetsOf(id).filter((w) => w.group === "sampler")
                                       .map((w) => w.id)),
}));
"""

controls = layout.run(CONTROLS_JS, STATE, catalog=PROBE_CATALOG)

h3_slots = [slot["id"] for slot in catalog["families"][0]["weights"]]
check("the popover's rows are the piece's family's",
      controls["fields"], [h3_slots, [f"p_{name}" for name in h3_slots]])
check("...and so are its labels",
      controls["labels"], [h3_slots, [f"p_{name}" for name in h3_slots]])
check("...and which rows may be pinned to a device",
      controls["devices"][1], [f"p_{name}" for name in controls["devices"][0]])
check("both families route, so both draw the route row",
      controls["routing"], [True, True])
check("what a queue is refused over is the piece's family's",
      controls["required"][1],
      [f"p_{name}" for name in controls["required"][0]])
check("...and so is what the pill calls missing",
      controls["missing"][1], [f"p_{name}" for name in controls["missing"][0]])
check("the sampler row is the family's declared controls",
      controls["widgets"][0], controls["widgets"][1])

# And on the registered second family, where the answers genuinely differ:
# LTX ships one transformer, so there is no route row and no per-LoRA
# checkpoint control, and its sampler row is not H3's with pieces missing.

LTX_CONTROLS = """
const S = await import(process.argv[1]);
console.log(JSON.stringify({
  routing: [S.routing("h3"), S.routing("ltx25")],
  checkpoints: S.checkpointsOf("ltx25"),
  // An empty LTX block is missing the four a render always loads, and neither
  // of the two opt-in passes — an unfilled optional slot is an offer.
  missing: S.missingModels({}, S.requiredModels([], false, "ltx25"), "ltx25"),
  h3Row: S.widgetsOf("h3").filter((w) => w.group === "sampler").map((w) => w.id),
  ltxRow: S.widgetsOf("ltx25").filter((w) => w.group === "sampler").map((w) => w.id),
}));
"""

ltx_controls = layout.run(LTX_CONTROLS, STATE)

# ---- the duration head, as a capability ---------------------------------------
#
# The one thing LTX has that H3 does not. The control is gated on
# `canDo(piece, "duration")` rather than on the id, and the blob's flag means
# nothing on a family with no weights to answer it — both halves have to agree
# about that or the pill offers a length nobody predicts.

AUTO_JS = """
const S = await import(process.argv[1]);
const piece = (family) => {
  const t = S.emptyTimeline();
  t.family = family;
  t.segments = [S.emptySegment()];
  t.segments[0].auto_duration = true;
  return t;
};
const roundTrip = (family) => {
  const t = piece(family);
  S.syncTimeline(t);
  return JSON.parse(S.serializeTimeline(t)).segments[0].auto_duration ?? false;
};
console.log(JSON.stringify({
  canDo: [S.canDo(piece("h3"), "duration"), S.canDo(piece("ltx25"), "duration")],
  written: [roundTrip("h3"), roundTrip("ltx25")],
  // Switching away from the family that can predict drops the flag rather than
  // retargeting it: there is no nearest answer to "let the model choose".
  dropped: (() => {
    const t = piece("ltx25");
    S.setFamily(t, "h3");
    return t.segments[0].auto_duration;
  })(),
  // ...and the strip's totals say they are estimates while one is on.
  estimate: [S.hasAutoDuration(piece("h3")), S.hasAutoDuration(piece("ltx25"))],
}));
"""

auto = layout.run(AUTO_JS, STATE)

check("only the family with a duration head offers auto", auto["canDo"], [False, True])
check("the flag survives only on the family that can answer it",
      auto["written"], [False, True])
check("switching to a family that cannot predict drops it", auto["dropped"], False)
check("the strip calls its totals estimates only where one is live",
      auto["estimate"], [False, True])

# ---- the seam's boundary pin ----------------------------------------------------
#
# The third capability gate, and the one whose absence is the interesting case:
# H3 presents pictures to its text encoder alongside the prompt, so a blended
# seam can be asked to name the frame it lands on there as well. LTX 2.5 sends
# Gemma text and hands the run to `LTXVAddGuide` — one channel, and the boundary
# frame is already the run's last element — so there is nothing to pin twice and
# no switch to draw.

PIN_JS = """
const S = await import(process.argv[1]);
const strip = (family, extra) => {
  const t = S.emptyTimeline();
  t.family = family;
  const grid = S.featherGridOf(t);
  t.segments = [S.emptySegment(), S.emptySegment()];
  Object.assign(t.segments[1], { continue: true, feather: grid[2], ...extra });
  S.syncTimeline(t);
  return t;
};
const written = (family, extra) =>
  JSON.parse(S.serializeTimeline(strip(family, extra))).segments[1];
console.log(JSON.stringify({
  canDo: [S.canDo(strip("h3", {}), "seam_pin"),
          S.canDo(strip("ltx25", {}), "seam_pin")],
  // Set on both; only the family with a second channel keeps it.
  kept: [S.featherPin(strip("h3", { feather_pin: true }).segments[1],
                      strip("h3", { feather_pin: true })),
         S.featherPin(strip("ltx25", { feather_pin: true }).segments[1],
                      strip("ltx25", { feather_pin: true }))],
  written: [written("h3", { feather_pin: true }).feather_pin ?? false,
            written("ltx25", { feather_pin: true }).feather_pin ?? false],
  // ...and the pin goes with the blend it modifies.
  unblended: (() => {
    const t = strip("h3", { feather_pin: true });
    delete t.segments[1].feather;
    S.syncTimeline(t);
    return t.segments[1].feather_pin ?? false;
  })(),
  // Absent is the default on a plain blended seam, which is the whole fix.
  byDefault: written("h3", {}).feather_pin ?? false,
}));
"""

pins = layout.run(PIN_JS, STATE)
check("only a family that presents pictures offers the pin", pins["canDo"], [True, False])
check("...and only there does the flag mean anything", pins["kept"], [True, False])
check("...or get written to the blob", pins["written"], [True, False])
check("the pin is dropped with the blend it modifies", pins["unblended"], False)
check("a blended seam does not pin its boundary frame by default",
      pins["byDefault"], False)

# ---- multishot advice ----------------------------------------------------------
#
# Both families cut inside one generation; what differs is the number each one's
# own guidance advises, and H3's gives none. So the strip marks a long pass only
# where there is a number to mark it against — a capability that is a *value*
# rather than a boolean, which is the case the manifest's shape has to survive.

SHOTS_JS = """
const S = await import(process.argv[1]);
const pass = (n) => ({ segments: Array.from({ length: n }, () => S.emptySegment()) });
const piece = (family) => { const t = S.emptyTimeline(); t.family = family; return t; };
console.log(JSON.stringify({
  advised: [S.advisedShots(piece("h3")), S.advisedShots(piece("ltx25"))],
  marked: [4, 5].map((n) => [S.overAdvisedShots(piece("h3"), pass(n)),
                             S.overAdvisedShots(piece("ltx25"), pass(n))]),
}));
"""

shots = layout.run(SHOTS_JS, STATE)
check("only LTX's guidance gives a number", shots["advised"], [None, 4])
check("a pass is marked past it, and never on a family with no number",
      shots["marked"], [[False, False], [False, True]])

check("LTX routes between nothing, so no route row and no LoRA checkpoint control",
      (ltx_controls["routing"], ltx_controls["checkpoints"]), ([True, False], []))
check("an empty LTX block is missing the four every render loads",
      ltx_controls["missing"], ["dit", "clip", "vae", "audio_vae"])
check("...and neither opt-in pass, which are offers rather than omissions",
      [name for name in ("duration_head", "upscaler")
       if name in ltx_controls["missing"]], [])
check("the two rows are different controls, not one with pieces missing",
      sorted(set(ltx_controls["ltxRow"]) - set(ltx_controls["h3Row"])),
      ["audio_cfg", "base_shift", "max_shift", "schedule", "stretch",
       "terminal", "video_cfg"])

passed("the piece names its family, and both halves read it off the piece")
