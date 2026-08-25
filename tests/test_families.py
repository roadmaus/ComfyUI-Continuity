"""The registry and the manifests: what exists, and that nothing drifted.

The manifests are built *from* the modules that render — `sampling.DEFAULTS`,
each family's own `models.SLOTS`, its `declare.py`, the family packages — so most drift is impossible
by construction. What this suite holds is the part construction cannot: that
every family the registry names actually serves a valid manifest, that the
catalog is JSON (it is a route's whole body), and that the derivations really
do land on the source values they claim to.

Runs standalone, no torch and no ComfyUI — the manifests are pure, which is
the property that lets the frontend's mirror suites read them later.
"""

import glob
import json
import os

import layout
from harness import FAILURES, check, passed

_pkg = layout.load("canvas", "accel", "sampling", "contextir", "compile",
                   "compile_image", "models", "registry", "manifest",
                   "still", "krea2_still", "ideogram4_still",
                   "grammar", "h3_declare", "h3_models", "h3_grammar",
                   "ltx25_declare",
                   "ltx25_models", "ltx25_sampling")
H3 = _pkg.h3_declare.RULES
h3slots = _pkg.h3_models
LTX25 = _pkg.ltx25_declare.RULES
canvas = _pkg.canvas
sampling = _pkg.sampling
models = _pkg.models
registry = _pkg.registry
manifest = _pkg.manifest
grammar = _pkg.grammar
ci = _pkg.compile_image
h3s = _pkg.still
k2 = _pkg.krea2_still
i4 = _pkg.ideogram4_still
lx = _pkg.ltx25_models
lxs = _pkg.ltx25_sampling

catalog = manifest.catalog()

# ---- discovery ---------------------------------------------------------------
#
# The registry walks `families/` for declarations rather than carrying tables
# keyed by id. What that buys is that a family becomes real by existing; what it
# costs is that a declaration missing a field fails somewhere downstream instead
# of at the family. So this is the field list, checked at the source.

DECLARES = ("ID", "LABEL", "ORDER", "PRODUCES", "STILL_ARCH", "PROMPT_PIPELINE",
            "LORA_STACK", "DURATION_HEAD", "ROUTED", "RULES")

# A video family also declares the graph node that is its boundary; a still-only
# family has no such node and no such field.
VIDEO_DECLARES = ("SEGMENT_NODE",)

check("every family package was discovered",
      sorted(registry.FAMILIES),
      sorted(os.path.basename(os.path.dirname(path))
             for path in glob.glob(os.path.join(layout.PY_ROOT, "families",
                                                "*", "declare.py"))))

for family in registry.FAMILIES:
    module = registry.DECLARATION[family]
    missing = [field for field in DECLARES if not hasattr(module, field)]
    check(f"{family} declares every field", missing, [])
    check(f"{family}'s declaration names itself", module.ID, family)
    # A video family has canvas arithmetic and a still-only family has none.
    # `registry.RULES` keys off exactly that, and `compile.rules_of` would hand
    # back None to arithmetic that cannot use it.
    check(f"{family} declares rules iff it renders video",
          module.RULES is not None, "video" in module.PRODUCES)
    if "video" in module.PRODUCES:
        missing = [field for field in VIDEO_DECLARES if not hasattr(module, field)]
        check(f"{family} declares its segment node", missing, [])

# Two families must not claim one node id: the registry key is what ComfyUI
# dispatches on, and a shared one would route the wrong family's payload.
segments = [m.SEGMENT_NODE for m in registry.DECLARED
            if "video" in m.PRODUCES]
check("every video family has a segment node of its own",
      len(set(segments)), len(segments))

check("the families are ordered by their own ORDER",
      list(registry.FAMILIES),
      [m.ID for m in sorted(registry.DECLARED, key=lambda m: (m.ORDER, m.ID))])
check("the frame grids are the declarations'",
      registry.RULES,
      {m.ID: m.RULES for m in registry.DECLARED if m.RULES})

# ---- the grammars ------------------------------------------------------------
#
# How a family reads a request — its caps, its mode names, its routing rule,
# what its encoder is sent. All four were `compile.py`'s, answered H3's way for
# every family; they are the family's now, and the manifest serves what the
# compiler will actually use rather than a second copy of it.

for family in registry.video_families():
    g = grammar.of(family)
    served = next(m for m in catalog["families"] if m["id"] == family)

    check(f"{family}'s served modes are its grammar's", served["modes"],
          dict(g.modes))
    check(f"{family}'s served caps are its grammar's",
          served["reference"]["max"],
          {"image": g.max_images, "video": g.max_videos,
           "audio": g.max_audios, "files": g.max_files})

    # Every shape has a name, so `Grammar.mode` cannot reach for a missing key
    # — `reference` excepted, which a family may decline to distinguish.
    missing = [shape for shape in ("opens_closes", "opens", "closes", "text")
               if shape not in g.modes]
    check(f"{family} names every payload shape", missing, [])
    # ...and no two shapes share a name, or a card would say one thing about two
    # different payloads.
    check(f"{family}'s mode names are distinct",
          len(set(g.modes.values())), len(g.modes))

    # What routes, and what it routes to. A family that routes between nothing
    # answers "" and means it; one that does must name slots it actually has.
    if registry.ROUTED[family]:
        for name in g.modes.values():
            check(f"{family}'s mode {name} routes to a slot it declares",
                  g.checkpoint(name) in registry.ROUTED[family], True)
    else:
        check(f"{family} routes nowhere",
              [g.checkpoint(name) for name in g.modes.values()],
              [""] * len(g.modes))

# ---- the catalog is a route body ---------------------------------------------

try:
    json.dumps(catalog)
except TypeError as exc:
    FAILURES.append(f"the catalog does not serialise to JSON: {exc}")

check("every registered family is served",
      [m["id"] for m in catalog["families"]], list(registry.FAMILIES))
check("the arch pill's map is the registry's",
      catalog["still_arches"], registry.STILL_ARCHES)
check("the default arch names a registered family",
      registry.STILL_ARCHES[catalog["default_still_arch"]] in registry.FAMILIES,
      True)

for m in catalog["families"]:
    check(f"{m['id']} produces what the registry says",
          m["produces"], sorted(registry.PRODUCES[m["id"]]))

# Every still producer answers the still surface; the arch map covers exactly
# the still producers.
still_families = {f for f in registry.FAMILIES if "still" in registry.PRODUCES[f]}
check("the arch map reaches every still family",
      set(registry.STILL_ARCHES.values()), still_families)
for arch in registry.STILL_ARCHES:
    module = registry.still(arch)
    check(f"{arch} answers the still surface",
          (callable(getattr(module, "compile_still", None)),
           callable(getattr(module, "emit_still", None))),
          (True, True))

# ---- a malformed manifest is refused by name ---------------------------------

try:
    manifest.check({"id": "bogus", "label": "x"})
except ValueError as exc:
    if "bogus" not in str(exc):
        FAILURES.append(f"a broken manifest is not refused by name: {exc}")
else:
    FAILURES.append("a manifest with no widgets was not refused")

try:
    manifest.widget("x", "dial", label="x", group="sampler")
except ValueError as exc:
    if "dial" not in str(exc):
        FAILURES.append(f"an unknown widget type is not refused by name: {exc}")
else:
    FAILURES.append("an unknown widget type was not refused")

# ---- H3 ----------------------------------------------------------------------

h3 = manifest.describe("h3")
widgets = {w["id"]: w for w in h3["widgets"]}

# The manifest's row is the blob's row: every `sampling.DEFAULTS` field is a
# control, each carrying that same default. Neither the seed (a genuine
# widget) nor the dead `sage` slot appears.
check("h3 declares the blob row exactly",
      sorted(widgets), sorted(sampling.DEFAULTS))
for name, entry in widgets.items():
    check(f"h3 {name} default is sampling.DEFAULTS'",
          entry["default"], sampling.DEFAULTS[name])

check("h3 combos with options carry the accel lists",
      (widgets["block_cache"]["options"], widgets["attention"]["options"]),
      (_pkg.accel.BLOCK_CACHE_MODES, _pkg.accel.ATTENTION_MODES))
check("core-owned combos declare no options — the node schema is the list",
      ("options" in widgets["sampler_name"], "options" in widgets["scheduler"]),
      (False, False))

check("h3 weight slots are the slot table, in its order",
      [w["id"] for w in h3["weights"]], list(h3slots.SLOTS))
for entry in h3["weights"]:
    slot = h3slots.SLOTS[entry["id"]]
    check(f"h3 slot {entry['id']} mirrors the table",
          (entry["folder"], entry["label"], entry["loads"],
           entry["routed"], entry["audio"]),
          (slot.folder, slot.label, bool(slot.loader),
           slot.routed, slot.audio))

check("h3 routes are the family's own ROUTES",
      (h3["routes"]["options"], h3["routes"]["default"]),
      (h3slots.ROUTES, models.DEFAULT_ROUTE))

# The derivation targets are routed slots, and the mode names are compile.py's
# own vocabulary — the frontend shows exactly what the compiler will say.
for key in ("reference", "plain", "timeline"):
    check(f"h3 routes[{key}] is a routed slot",
          h3["routes"][key] in h3slots.ROUTED_SLOTS, True)
# The names the manifest serves are the grammar's own — which is what the
# compiler stamps on the payload, so the card and the encode path cannot say
# different things about what a generation is.
check("h3 mode names are the grammar's",
      h3["modes"], dict(_pkg.h3_grammar.GRAMMAR.modes))
check("...and its caps are too",
      (h3["reference"]["max"]["image"], h3["reference"]["max"]["video"],
       h3["reference"]["max"]["audio"], h3["reference"]["max"]["files"]),
      (_pkg.h3_grammar.GRAMMAR.max_images, _pkg.h3_grammar.GRAMMAR.max_videos,
       _pkg.h3_grammar.GRAMMAR.max_audios, _pkg.h3_grammar.GRAMMAR.max_files))

# The turbo switch resets to the node's own defaults, and the lead-in
# stepper's reach is the server's — the two halves that must not drift.
_turbo = h3["capabilities"]["turbo"]
check("h3 turbo reset is sampling.DEFAULTS",
      _turbo["reset"],
      {key: sampling.DEFAULTS[key] for key in _turbo["reset"]})
check("h3 turbo lead max is settings.MAX_LEAD_IN",
      _turbo["lead_max"], _pkg.settings.MAX_LEAD_IN)

# The served latent grid generates still.latent_frames — over every offered
# length and one past the base, where the formula's branch flips.
_grid = h3["still"]["latent"]
for frames in list(h3["still"]["lengths"]) + [_grid["base_frames"] + _grid["frame_step"]]:
    derived = (_grid["base_latent"] if frames <= _grid["base_frames"] else
               (frames - _grid["base_frames"]) // _grid["frame_step"]
               * _grid["latent_step"] + _grid["base_latent"])
    check(f"latent grid at {frames} frames", derived, h3s.latent_frames(frames))

frames = h3["canvas"]["frames"]
legal = canvas.legal_frame_counts(H3)
check("the manifest's frame grid generates the legal counts",
      [frames["offset"], legal[1] - legal[0]],
      [legal[0], frames["step"]])
check("h3 canvas carries the trained range and the snap",
      (h3["canvas"]["multiple"], frames["trained_min"], frames["trained_max"],
       h3["canvas"]["fps"]),
      (H3.multiple, H3.trained_min_frames,
       H3.trained_max_frames, {"value": H3.fps, "fixed": True}))
check("h3 aspects are the presets", h3["canvas"]["aspects"],
      H3.aspects)
check("h3 still block is families/h3/still.py's",
      (h3["still"]["arch"], h3["still"]["lengths"],
       h3["still"]["prompt_modes"]),
      (h3s.ARCH, list(h3s.STILL_LENGTHS), list(h3s.PROMPT_MODES)))

# ---- LTX 2.5 -----------------------------------------------------------------
#
# The second video family, and the first manifest whose shape differs from H3's
# rather than repeating it. What is checked here is what construction cannot
# give: that the declarations really are the family's own modules', and that
# the two families differ where the architectures do — a manifest that quietly
# inherited H3's frame grid or H3's routing would pass every other suite.

ltx = manifest.describe("ltx25")
lwidgets = {w["id"]: w for w in ltx["widgets"]}

check("ltx25 renders video only", ltx["produces"], ["video"])
check("ltx25 declares the sampler row exactly",
      sorted(lwidgets), sorted(lxs.DEFAULTS))
for name, entry in lwidgets.items():
    check(f"ltx25 {name} default is sampling.DEFAULTS'",
          entry["default"], lxs.DEFAULTS[name])
check("core-owned combos declare no options — the node schema is the list",
      "options" in lwidgets["sampler_name"], False)

# The row is the architecture's, not a copy of H3's: two CFG scales for the
# packed AV latent, no `scheduler` combo (LTXVScheduler *is* the scheduler),
# and the shift pair the model patch and the schedule must agree on.
check("ltx25 guides the two modalities apart",
      ("video_cfg" in lwidgets, "audio_cfg" in lwidgets, "cfg" in lwidgets),
      (True, True, False))
check("ltx25 has no scheduler combo — the scheduler is a node",
      "scheduler" in lwidgets, False)

check("ltx25 weight slots are the family's slot table, in its order",
      [w["id"] for w in ltx["weights"]], list(lx.SLOTS))
for entry in ltx["weights"]:
    slot = lx.SLOTS[entry["id"]]
    check(f"ltx25 slot {entry['id']} mirrors the table",
          (entry["folder"], entry["label"], entry["loads"],
           entry["routed"], entry["audio"], entry["required"]),
          (slot.folder, slot.label, bool(slot.loader),
           slot.routed, slot.audio, not slot.optional))

# One transformer, so nothing is routed and there is no route control at all —
# the shape `state.js`' NO_ROUTING fallback answers for.
check("ltx25 routes nothing", [w["id"] for w in ltx["weights"] if w["routed"]], [])
check("ltx25 declares no routing block", "routes" in ltx, False)
check("ltx25 required slots are the table's",
      [w["id"] for w in ltx["weights"] if w["required"]], lx.REQUIRED)
check("both opt-in passes are optional",
      sorted(w["id"] for w in ltx["weights"] if not w["required"]),
      ["duration_head", "upscaler"])

# A device can only be pinned where ComfyUI-MultiGPU has a wrapper, which is
# the four core loaders — not the patch loader, not the upscale loader.
check("ltx25 pins devices only where a wrapper exists",
      [w["id"] for w in ltx["weights"] if w["device"]],
      [name for name, slot in lx.SLOTS.items() if slot.loader in models.MULTIGPU])

# The canvas is LTX25's, and it is not H3's: an 8n+1 grid against
# 17n+5, and a rate that is conditioning rather than a property of the weights.
lframes = ltx["canvas"]["frames"]
check("ltx25 canvas is LTX25",
      ltx["canvas"], manifest.canvas_block(LTX25))
check("ltx25 fps is conditioning, H3's is not",
      (ltx["canvas"]["fps"]["fixed"], h3["canvas"]["fps"]["fixed"]),
      (False, True))
check("ltx25 frames are the 8n+1 grid",
      (lframes["step"], lframes["offset"]), (8, 1))
llegal = canvas.legal_frame_counts(LTX25)
check("the manifest's frame grid generates the legal counts",
      [lframes["offset"], llegal[1] - llegal[0]], [llegal[0], lframes["step"]])
for frames in llegal[:200]:
    if frames % 8 != 1:
        FAILURES.append(f"ltx25 legal count {frames} is off the 8n+1 grid")
        break
check("ltx25 snaps to 32", ltx["canvas"]["multiple"], LTX25.multiple)

# The capability split, in both directions — the point of asking rather than
# branching on an id.
lcaps = ltx["capabilities"]
check("ltx25 has the duration head H3 has no answer to",
      (bool(lcaps.get("duration")), bool(h3["capabilities"].get("duration"))),
      (True, False))
check("the duration capability names a real slot",
      lcaps["duration"]["slot"] in lx.SLOTS, True)
# Both families refine and neither means the same thing by it: H3 re-encodes
# the request at a larger canvas and re-samples, LTX runs a trained x2 latent
# upscaler between two sittings of one schedule. So the capability is declared
# as *what kind* rather than as a flag, and the frontend's copy reads it.
check("ltx25 refines through its own latent upscaler",
      (lcaps["refine"]["kind"], lcaps["refine"]["factor"]),
      ("latent_upscale", 2))
check("...and the slot it needs is a real one",
      lcaps["refine"]["slot"] in lx.SLOTS, True)
check("...which is optional, because the pass is a choice",
      lx.SLOTS[lcaps["refine"]["slot"]].optional, True)
check("ltx25 lacks the face pass H3 has",
      (lcaps["face"], h3["capabilities"]["refine"], h3["capabilities"]["face"]),
      (False, True, True))
check("ltx25 always makes sound", lcaps["audio"], True)
check("ltx25 has no turbo switch — the distilled file is a pick, not a LoRA",
      "turbo" in lcaps, False)
check("ltx25 prompts in plain prose", ltx["prompt"]["pipeline"], "plain")
check("ltx25 has no pre-stage still", "still" in ltx, False)

# The encoder is one file through the ordinary CLIPLoader, and the audio VAE
# one pick from `vae` — the LTX 2.5 layout, not the Gemma-3 recipe's two-file
# encoder and `checkpoints` audio VAE.
check("the encoder is one CLIPLoader pick typed ltxv",
      (lx.SLOTS["clip"].loader, lx.SLOTS["clip"].input, lx.SLOTS["clip"].extra),
      ("CLIPLoader", "clip_name", {"type": lx.CLIP_TYPE}))
check("both VAEs come out of models/vae through VAELoader",
      [(lx.SLOTS[n].folder, lx.SLOTS[n].loader) for n in ("vae", "audio_vae")],
      [("vae", "VAELoader"), ("vae", "VAELoader")])

# ---- Krea 2 ------------------------------------------------------------------

krea = manifest.describe("krea2")
kwidgets = {w["id"]: w for w in krea["widgets"]}
for name in ("steps", "cfg", "sampler_name", "scheduler"):
    check(f"krea2 {name} default is KREA_RAW's",
          kwidgets[name]["default"], k2.KREA_RAW[name])
check("krea2 weight slots are the family's fields",
      [w["id"] for w in krea["weights"]], list(k2.FIELDS))
check("krea2 turbo capability carries the presets",
      krea["capabilities"]["turbo"],
      {"steps": k2.TURBO_STEPS, "row": k2.KREA_TURBO,
       "default_quality": k2.DEFAULT_TURBO_QUALITY})
check("krea2 reference cap is the encoder's",
      krea["prompt"]["max_refs"], ci.MAX_STYLE_REFS)
check("krea2 canvas is the shared /16 grid",
      (krea["canvas"]["multiple"], krea["canvas"]["max_pixels"]),
      (ci.CANVAS_MULTIPLE, ci.MAX_PIXELS))

# ---- Ideogram 4 --------------------------------------------------------------

ideo = manifest.describe("ideogram4")
iwidgets = {w["id"]: w for w in ideo["widgets"]}
check("ideogram quality options are the preset table's",
      iwidgets["quality"]["options"], list(i4.IDEOGRAM_QUALITIES))
check("ideogram cfg default is the template's",
      iwidgets["cfg"]["default"], i4.IDEOGRAM_CFG)
check("ideogram reads no references",
      (ideo["prompt"]["max_refs"], ideo["prompt"]["ordinal"]), (0, None))
check("only the unconditional checkpoint is optional",
      [w["id"] for w in ideo["weights"] if not w.get("required", True)],
      ["uncond_model"])

passed("the registry serves every family and the manifests hold their sources")
