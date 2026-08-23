"""Which family renders a piece is a field of the piece, and everything reads it.

Phase 1 of `docs/PLAN-ltx25.md`. `manifest.js` exported `VIDEO` — *the* family
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

_pkg = layout.load("canvas", "registry", "manifest", "contextir", "subjects", "compile")
compiler, registry = _pkg.compile, _pkg.registry
catalog = _pkg.manifest.catalog()

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
    ("a piece naming a family that is not installed",
     {"version": 2, "segments": [], "family": "ltx25"}, "h3"),
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

check("the probe is listed", probed["families"], ["h3", "probe"])
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

passed("the piece names its family, and both halves read it off the piece")
