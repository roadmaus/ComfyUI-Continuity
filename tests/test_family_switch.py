"""What survives a family switch, and what a family with one transformer routes.

Three faults, one root. A piece switched from H3 to LTX 2.5 came out saying two
of its weights were missing when all six were picked; the H3 distillation LoRA
the turbo switch had thrown was still in the stack, still patched onto the
render, with no switch left that admitted to owning it; and the six files picked
for the family being left were thrown away, so a trip back meant picking them
again.

The first two are the same defect. The weights layer learned about families in
phase 1 — `modelFields`, `requiredModels`, `emptyModels` all take one — but the
*routing* layer did not: `checkpoint`, `timelineCheckpoints`, `loraModes` and
`compile._resolve_checkpoint` all answered with H3's pair whatever the piece
said. So an LTX piece required a slot called `fl2va` that its manifest has never
heard of (drawn as missing weights, since a family's label table has no name for
it), and a LoRA whose `modes` LTX could not parse fell back to "claims both of
H3's" — which is what put an H3 distill on a 22B LTX transformer.

**A family that ships one transformer routes between nothing.** That is the rule
this suite holds, on both sides: no checkpoint is derived, none may be pinned,
none is required, and a LoRA claims nothing — so every enabled entry is patched
onto the one set of weights there is.

The third is a memory: a piece sets its outgoing weights aside under the family
they belong to (`models_spare`), and the machine remembers the last block picked
for each family (`settings.weights`) so a node that has never been switched
still comes up filled. The sampler row travels the same way and for a sharper
reason — `steps` and `sampler_name` are spelled the same on both families and
mean different things, so a row carried across a switch samples the new family
at the old one's numbers.

    python3 tests/test_family_switch.py

Skips itself if node is not installed.
"""

import json

import layout

layout.skip_without_node()

from harness import FAILURES, check, passed

_pkg = layout.load("canvas", "registry", "manifest", "contextir", "subjects",
                   "compile", "settings")
compiler, registry, settings = _pkg.compile, _pkg.registry, _pkg.settings

STATE = layout.js("state.js")


def _sampling_default(family, field):
    """One family's own default for a sampler field, off its manifest — the
    numbers a switched piece has to land on rather than inherit."""
    for widget in _pkg.manifest.describe(family)["widgets"]:
        if widget["id"] == field:
            return widget["default"]
    return None

# ---- the registry's table ----------------------------------------------------

check("H3 routes between its two checkpoints",
      registry.ROUTED["h3"], ("fl2va", "ref2va"))
check("LTX 2.5 ships one transformer and routes between nothing",
      registry.ROUTED["ltx25"], ())
check("every family the registry lists says which",
      sorted(registry.ROUTED), sorted(registry.FAMILIES))
check("compile's own pair is the default family's",
      compiler.CHECKPOINTS, registry.ROUTED[registry.DEFAULT_VIDEO])

# The manifests serve the same answer to the frontend, off each family's slot
# table. Two spellings of one fact is exactly what this holds together.
for family in registry.video_families():
    served = tuple(slot["id"] for slot in _pkg.manifest.describe(family)["weights"]
                   if slot.get("routed"))
    check(f"{family}: the manifest's routed slots are the registry's",
          served, registry.ROUTED[family])

# ---- compile.py: what a non-routing family resolves --------------------------

TURBO = "minimax_h3_turbo_v4.safetensors"
STACK = [
    # Aimed at one H3 checkpoint, which is a claim LTX cannot read.
    {"name": TURBO, "strength": 1.0, "modes": ["fl2va"]},
    {"name": "grain.safetensors", "strength": 0.8},
    {"name": "muted.safetensors", "strength": 1.0, "enabled": False},
]

check("an LTX generation routes to no checkpoint",
      compiler._resolve_checkpoint("T2VA", "auto", "ltx25"), ("", False))
# A pin is a field the piece has stopped having a use for, not an error: the
# card kept it from when the piece was on H3, exactly as it keeps `auto_duration`
# on a family with no duration head.
check("...and a pin left over from the family it was switched off is ignored",
      compiler._resolve_checkpoint("T2VA", "fl2va", "ltx25"), ("", False))
check("H3 still derives its own", compiler._resolve_checkpoint("T2VA", "auto", "h3"),
      ("fl2va", False))
try:
    compiler._resolve_checkpoint("T2VA", "nonsense", "h3")
    FAILURES.append("H3 should still refuse a checkpoint that is not one of its two")
except compiler.CompileError:
    pass

check("a LoRA claims nothing on a family that routes between nothing",
      compiler.lora_modes(STACK[0], "ltx25"), ())
check("...and both of H3's when it names neither",
      compiler.lora_modes(STACK[1], "h3"), ("fl2va", "ref2va"))

check("with no checkpoint to select on, every enabled LoRA is patched",
      [entry["name"] for entry in compiler.active_loras(STACK, "", "ltx25")],
      [TURBO, "grain.safetensors"])
check("...and H3 still selects on the claim",
      [entry["name"] for entry in compiler.active_loras(STACK, "ref2va", "h3")],
      ["grain.safetensors"])

# The whole request, since that is the path the render takes.
PIECE = {
    "version": 2, "family": "ltx25", "short_edge": 768,
    "models": {"dit": "dit.safetensors"},
    "segments": [{"prompt": "a street", "duration_s": 4, "checkpoint": "fl2va",
                  "loras": list(STACK)}],
}
compiled = compiler.compile_single(json.loads(json.dumps(PIECE)))
check("a compiled LTX segment names no checkpoint", compiled.checkpoint, "")
check("...and is not marked as pinned to one", compiled.checkpoint_pinned, False)

# ---- settings.py: the machine's memory ---------------------------------------

check("a fresh install remembers no weights", settings.DEFAULTS["weights"], {})
MEMORY = {"h3": {"fl2va": "h3.safetensors", "route": "ref2va",
                 "devices": {"clip": "cuda:1"}},
          "ltx25": {"dit": "ltx.safetensors"}}
check("a block round-trips as written", settings.clean({"weights": MEMORY})["weights"],
      MEMORY)
check("an empty block is not stored at all",
      settings.clean({"weights": {"h3": {}}})["weights"], {})
for bad in ({"weights": 7}, {"weights": {"h3": "a-file.safetensors"}},
            {"weights": {"h3": {"dit": 7}}}):
    try:
        settings.clean(bad)
        FAILURES.append(f"settings should refuse {bad!r}")
    except ValueError:
        pass

check("the spare blocks are a field of the piece, so a v1 lift carries them up",
      ("models_spare" in compiler.PIECE_FIELDS,
       "sampling_spare" in compiler.PIECE_FIELDS), (True, True))
# Why the row cannot be carried across a switch: both families declare a field
# called `steps`, and 20 of H3's are 8 of LTX's.
check("the two families' step counts are their own",
      [_sampling_default("h3", "steps"), _sampling_default("ltx25", "steps")],
      [20, 8])

# ---- the frontend ------------------------------------------------------------

FRONT = """
const S = await import(process.argv[1]);
const stack = JSON.parse(process.argv[2]);
const turbo = process.argv[3];

// A piece set up on H3: six files, a thrown turbo switch, a LoRA of the user's
// own, and a card pinned to a checkpoint.
const piece = S.parseTimeline(JSON.stringify({
  version: 2, prompt: "a street",
  models: { route: "ref2va",
            ...Object.fromEntries(["fl2va", "ref2va", "clip", "vae", "audio_vae",
                                   "preview", "sam3"].map((s) => [s, `h3-${s}.safetensors`])) },
  turbo: { lora: turbo, on: true,
           // What the row said before the switch was thrown, which is what
           // switching off puts back — and what a switch away has to set
           // aside, rather than the distillation's own 6.
           saved: { steps: 20, sampler_name: "res_multistep", scheduler: "simple",
                    shift_video: 12, shift_audio: 3 } },
  sampling: { steps: 6, sampler_name: "euler", scheduler: "beta", cfg: 1 },
  loras: stack,
  segments: [{ prompt: "one", checkpoint: "fl2va" }],
}));

const h3Models = { ...piece.models };
S.setFamily(piece, "ltx25");
const onLtx = JSON.parse(JSON.stringify(piece));

// Every slot an LTX render actually loads, filled by hand — the state the pill
// used to call "2 weights missing".
for (const slot of ["dit", "clip", "vae", "audio_vae"]) {
  piece.models[slot] = `${slot}.safetensors`;
}
const targets = S.timelineCheckpoints(piece);
const missing = S.missingModels(
  piece.models,
  S.requiredModels(S.routedCheckpoints(piece.models, targets), false, "ltx25"),
  "ltx25");
const blob = JSON.parse(S.serializeTimeline(piece));

// ...and back, which is where the memory earns itself.
S.setFamily(piece, "h3");

// A piece that has never been on LTX, switched to it with the machine's memory
// in hand: nothing set aside, and the files come off the last node that picked
// them.
const fresh = S.parseTimeline("{}");
S.setFamily(fresh, "ltx25", { ltx25: { dit: "remembered.safetensors" } });

console.log(JSON.stringify({
  // The row is the family's: reset on the way out, set aside under the family
  // that dialled it, released from the turbo switch first.
  samplingOnLtx: onLtx.sampling,
  spareRowOnLtx: onLtx.sampling_spare,
  restoredRow: piece.sampling,
  // Nothing to route between, so nothing derives, pins or is required.
  routing: S.routing("ltx25"),
  derived: S.derivedCheckpoint(piece.segments[0], "ltx25"),
  checkpoint: S.checkpoint(piece.segments[0], "ltx25"),
  canPin: S.canPinCheckpoint(piece.segments[0], "ltx25"),
  targets, missing,
  // The claim an H3 LoRA carries means nothing here, and reading it as "both of
  // H3's" is what made the piece patch a distill it had no switch for.
  claim: S.loraModes(stack[0], "ltx25"),
  active: S.activeGlobalLoras(piece).map((entry) => entry.name),
  // The switch's own entry goes with the switch; the user's file stays.
  stackOnLtx: onLtx.loras.map((entry) => entry.name),
  turboOnLtx: onLtx.turbo.lora,
  // Set aside under the family it belongs to, and handed back on return.
  spareOnLtx: onLtx.models_spare,
  restored: piece.models,
  h3Models,
  spareOnH3: piece.models_spare,
  // The blob carries the stash, and only where there is one.
  blobSpare: blob.models_spare,
  freshBlob: "models_spare" in JSON.parse(S.serializeTimeline(S.parseTimeline("{}"))),
  remembered: fresh.models.dit,
  // A memory never talks over what the piece already says.
  kept: (() => {
    const held = S.parseTimeline(JSON.stringify({ version: 2, family: "ltx25",
                                                  models: { dit: "mine.safetensors" } }));
    S.adoptRemembered(held.models, { ltx25: { dit: "theirs.safetensors",
                                              clip: "theirs-clip.safetensors" } },
                      "ltx25");
    return [held.models.dit, held.models.clip];
  })(),
}));
"""

front = layout.run(FRONT, STATE, STACK, TURBO)

check("the frontend agrees LTX routes between nothing", front["routing"], False)
check("...so nothing is derived", front["derived"], None)
check("...nothing is routed to", front["checkpoint"], None)
check("...nothing may be pinned", front["canPin"], False)
check("...and a strip on it targets no checkpoint", front["targets"], [])
check("an LTX piece with its four files picked is missing nothing",
      front["missing"], [])
check("an H3 LoRA's claim is meaningless here", front["claim"], [])
check("...so every enabled entry is in the run",
      front["active"], ["grain.safetensors"])

check("the turbo LoRA leaves with the switch that threw it",
      front["stackOnLtx"], ["grain.safetensors", "muted.safetensors"])
check("...and the switch itself is reset", front["turboOnLtx"], "")

check("the outgoing weights are set aside under their own family",
      front["spareOnLtx"], {"h3": {**{s: f"h3-{s}.safetensors" for s in
                                      ("fl2va", "ref2va", "clip", "vae",
                                       "audio_vae", "preview", "sam3")},
                                   "route": "ref2va"}})
check("...and come back on the way home", front["restored"], front["h3Models"])
check("...with LTX's own now in the stash",
      front["spareOnH3"], {"ltx25": {slot: f"{slot}.safetensors" for slot in
                                     ("dit", "clip", "vae", "audio_vae")}})
check("the stash survives a save", front["blobSpare"],
      {"h3": front["spareOnLtx"]["h3"]})
check("a piece that never switched writes none", front["freshBlob"], False)

check("the sampler row does not follow the piece onto another family",
      front["samplingOnLtx"], {})
check("...it is set aside as the row that was dialled, the turbo throw undone",
      front["spareRowOnLtx"],
      {"h3": {"steps": 20, "sampler_name": "res_multistep", "scheduler": "simple",
              "shift_video": 12, "shift_audio": 3, "cfg": 1}})
check("...and comes back with the family that dialled it",
      front["restoredRow"], front["spareRowOnLtx"]["h3"])

check("a family the piece has never been on comes off the machine's memory",
      front["remembered"], "remembered.safetensors")
check("...which fills an empty row and never overwrites a picked one",
      front["kept"], ["mine.safetensors", "theirs-clip.safetensors"])

passed("a family with one transformer routes between nothing, and a switch "
       "keeps the weights and the row it was given")
