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
                   "h3image_still", "h3still_still", "krea2_still", "ideogram4_still", "flux2klein_still",
                   "qwen21_still", "moss_still", "visionweights",
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
h3i = _pkg.h3image_still
h3s = _pkg.h3still_still
k2 = _pkg.krea2_still
i4 = _pkg.ideogram4_still
kl = _pkg.flux2klein_still
q21 = _pkg.qwen21_still
ms = _pkg.moss_still
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
           entry["routed"], entry["audio"], entry["required"]),
          (slot.folder, slot.label, bool(slot.loader),
           slot.routed, slot.audio, not slot.optional))

# The files an H3 render never asks for by itself: the background remover the
# picker's scissors run, the ControlNet branch a guide loads, and the trained
# latent upscaler the refine pass draws with when one is picked. The first two
# were served without the flag, so everything reading the catalog demanded
# them of every render — `models.check` never did, which is how the two
# disagreed.
check("the opt-in H3 slots say they are opt-in",
      sorted(w["id"] for w in h3["weights"] if not w["required"]),
      ["control", "cutout", "upscaler"])

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

# H3 renders video and nothing else: its stills are MiniMax H3 Image's.
check("h3 serves no pre-stage still block", "still" in h3, False)
check("h3 produces video only, and names no pill arch",
      (sorted(registry.PRODUCES["h3"]), _pkg.h3_declare.STILL_ARCH), (["video"], None))

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
# Every slot a render can go without: the two opt-in passes, the Ingredients
# IC-LoRA (needed only where a card cites a reference), the background remover
# (needed only while the cutout toggle is on) and the subject picker (needed
# only when the sheet editor is given clicks).
check("the opt-in slots are optional",
      sorted(w["id"] for w in ltx["weights"] if not w["required"]),
      ["cutout", "duration_head", "ic_lora", "sam3", "upscaler"])

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
check("ltx25 always makes sound", bool(lcaps["audio"]), True)
# ...and can be handed some. `supplied` is what the sound lane is gated on, and
# it is a claim about the latent rather than about this pack: both video
# families pack a maskable audio stream, so a track can be fixed instead of
# described. A family that generated its sound in a second pass would say False
# here and the lane would not draw.
check("both video families take a supplied track",
      [manifest.describe(family)["capabilities"]["audio"]["supplied"]
       for family in sorted(registry.video_families())],
      [True, True])
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
       "default_quality": k2.DEFAULT_TURBO_QUALITY,
       "lora": True, "default_strength": 1.0, "checkpoint": True,
       "hints": {"family": "krea"}})
check("krea2 declares both ways to be fast — the distilled file and the LoRA",
      (krea["capabilities"]["turbo"]["checkpoint"],
       krea["capabilities"]["turbo"]["lora"]), (True, True))
check("krea2 reads references through an edit LoRA, with no layout to pick",
      (krea["capabilities"]["refs"]["methods"],
       krea["capabilities"]["refs"]["default_method"],
       krea["capabilities"]["refs"]["needs_lora"]),
      ([], None, True))
check("...and names the two V2 LoRAs it reads them through",
      [kind for _, kind in krea["capabilities"]["refs"]["edit"]["kinds"]],
      ["identity", "general"])
check("krea2 reference cap is the scene and subject slots",
      krea["prompt"]["max_refs"], k2.REFS_LIMIT)
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
check("ideogram turbo is a LoRA and only a LoRA — there is no distilled file",
      (ideo["capabilities"]["turbo"]["lora"],
       ideo["capabilities"]["turbo"]["checkpoint"],
       ideo["capabilities"]["turbo"]["steps"]),
      (True, False, i4.TURBO_STEPS))
check("every quality preset names its polish tail",
      {name: preset["polish"] for name, preset in ideo["capabilities"]["qualities"].items()},
      {name: preset["polish"] for name, preset in i4.IDEOGRAM_QUALITIES.items()})

# ---- Flux 2 Klein ------------------------------------------------------------

klein = manifest.describe("flux2klein")
klwidgets = {w["id"]: w for w in klein["widgets"]}
for name in ("steps", "cfg", "sampler_name"):
    check(f"flux2klein {name} default is KLEIN_BASE's",
          klwidgets[name]["default"], kl.KLEIN_BASE[name])
check("flux2klein declares no scheduler — the schedule is Flux2Scheduler's",
      "scheduler" in klwidgets, False)
check("flux2klein weight slots are the family's fields",
      [w["id"] for w in klein["weights"]], list(kl.FIELDS))
check("flux2klein turbo is the distilled checkpoint and only that",
      klein["capabilities"]["turbo"],
      {"steps": kl.TURBO_STEPS, "row": kl.KLEIN_TURBO,
       "default_quality": kl.DEFAULT_TURBO_QUALITY,
       "lora": False, "checkpoint": True})
check("flux2klein references are native and the first can be the one edited",
      (klein["capabilities"]["refs"]["methods"],
       klein["capabilities"]["refs"]["needs_lora"],
       klein["capabilities"]["refs"]["edits_first"],
       klein["capabilities"]["refs"]["edit_first"]),
      ([], False, True, ci.EDIT_FIRST_FIELD))
check("flux2klein reference cap is the pack's own, not an encoder slot count",
      klein["prompt"]["max_refs"], kl.REFS_LIMIT)
check("flux2klein's matched encoder is the text-only cut, and that is declared",
      kl.REFS_NEED_VISION, False)
check("flux2klein canvas is the shared /16 grid",
      (klein["canvas"]["multiple"], klein["canvas"]["max_pixels"]),
      (ci.CANVAS_MULTIPLE, ci.MAX_PIXELS))

# ---- Qwen Image 2.1 ----------------------------------------------------------

qwen21 = manifest.describe("qwen21")
q21widgets = {w["id"]: w for w in qwen21["widgets"]}
for name in ("steps", "cfg", "sampler_name", "scheduler"):
    check(f"qwen21 {name} default is QWEN21_BASE's",
          q21widgets[name]["default"], q21.QWEN21_BASE[name])
check("qwen21 weight slots are the family's fields",
      [w["id"] for w in qwen21["weights"]], list(q21.FIELDS))
check("qwen21 wants its own VAE and the shared qwen_image encoder type",
      (q21.VAE_KIND, q21.CLIP_TYPE), ("qwen_image21", "qwen_image"))
check("qwen21 turbo is a LoRA and only a LoRA — there is no distilled file",
      qwen21["capabilities"]["turbo"],
      {"steps": q21.TURBO_STEPS, "row": q21.TURBO_ROW,
       "default_quality": q21.DEFAULT_TURBO_QUALITY,
       "lora": True, "default_strength": 1.0, "checkpoint": False,
       "hints": qwen21["capabilities"]["turbo"]["hints"]})
check("qwen21 references are native and the first can be the one edited",
      (qwen21["capabilities"]["refs"]["methods"],
       qwen21["capabilities"]["refs"]["needs_lora"],
       qwen21["capabilities"]["refs"]["edits_first"],
       qwen21["capabilities"]["refs"]["edit_first"]),
      ([], False, True, ci.EDIT_FIRST_FIELD))
check("qwen21 has no editions and no native-control table — one release",
      ("editions" in qwen21["capabilities"]["refs"],
       "native_control" in qwen21["capabilities"]["refs"]), (False, False))
check("qwen21 reference cap is the official workflow's ten, served to the UI",
      (qwen21["prompt"]["max_refs"], q21.REFS_LIMIT), (10, 10))
check("qwen21 cites pictures the way its tokenizer spells them",
      (q21.REFS_CITATION, qwen21["prompt"]["ordinal"]), ("<image{n}>", "<image N>"))
check("qwen21 canvas is the shared /16 grid",
      (qwen21["canvas"]["multiple"], qwen21["canvas"]["max_pixels"]),
      (ci.CANVAS_MULTIPLE, ci.MAX_PIXELS))

# ---- MiniMax H3 Image --------------------------------------------------------

h3img = manifest.describe("h3image")
h3iwidgets = {w["id"]: w for w in h3img["widgets"]}
for name in ("steps", "cfg", "sampler_name", "scheduler"):
    check(f"h3image {name} default is the template's six-step row",
          h3iwidgets[name]["default"], h3i.H3IMAGE_ROW[name])
check("h3image samples the checkpoint's six PDD heads at cfg 1",
      (h3i.H3IMAGE_ROW["steps"], h3i.H3IMAGE_ROW["cfg"]), (6, 1.0))
check("h3image weight slots are one DiT, the encoder and the image VAE",
      [w["id"] for w in h3img["weights"]], ["model", "clip", "vae"])
check("h3image wants the image VAE and H3's own encoder type",
      (h3i.VAE_KIND, h3i.CLIP_TYPE), ("h3_image", "minimax"))
check("h3image is the pill's frozen \"minimax\" arch",
      (registry.STILL_ARCHES.get("minimax"), h3i.ARCH, "h3image" in ci.ARCHES),
      ("h3image", "minimax", True))
check("h3image has no turbo — the distillation is the checkpoint",
      "turbo" in h3img["capabilities"], False)
check("h3image references are native and the first can be the one edited",
      (h3img["capabilities"]["refs"]["needs_lora"],
       h3img["capabilities"]["refs"]["edits_first"],
       h3img["capabilities"]["refs"]["edit_first"]),
      (False, True, ci.EDIT_FIRST_FIELD))
check("h3image cites pictures the way MiniMax's prompts do",
      (h3i.REFS_CITATION, h3img["prompt"]["ordinal"]), ("<Picture {n}>", "<Picture N>"))
check("h3image's guide is a mask over Picture 1, with nothing to load",
      (h3img["capabilities"]["control"]["method"],
       h3img["capabilities"]["control"]["tracings"], h3i.CONTROL_WEIGHTS),
      ("mask", ["matte"], False))
check("h3image canvas is its own: /32, the shared floor, up to 20 MP",
      {k: h3img["canvas"][k] for k in ("multiple", "min_short_edge", "max_short_edge",
                                      "max_long_edge", "max_pixels")},
      {"multiple": 32, "min_short_edge": 512, "max_short_edge": 4096,
       "max_long_edge": 6272, "max_pixels": 20 * 1024 * 1024})
check("...and the canvas resolves the card's 16 MP sizes",
      [ci.resolve_canvas(r, e, ci.canvas_of(h3i)) for r, e in
       ((1.0, 4096), (4 / 3, 3552), (16 / 9, 3072), (21 / 9, 2688))],
      [(4096, 4096), (4736, 3552), (5472, 3072), (6272, 2688)])
check("every other family keeps the shared canvas, byte for byte",
      [ci.resolve_canvas(r, e, ci.canvas_of(k2)) for r, e in ((16 / 9, 1024), (3.0, 2048))],
      [ci.resolve_canvas(r, e) for r, e in ((16 / 9, 1024), (3.0, 2048))])

# A pre-stage blob saved on the old H3 branch is lifted into the shared fields.
_old = {"arch": "minimax", "prompt": "", "minimax": {
    "frames": 22, "latent_index": 1,
    "request": {"prompt": "@img-1 at dusk", "aspect": "9:16",
                "assets": [{"handle": "img-1", "filename": "a.png", "kind": "image", "role": "reference"},
                           {"handle": "aud-1", "filename": "s.wav", "kind": "audio"}],
                "loras": [{"name": "x.safetensors", "strength": 0.5}]}}}
_mig = h3i.migrate(_old)
check("an old H3 still's request is lifted into the shared fields",
      (_mig["prompt"], _mig["refs"], _mig["loras"], _mig["aspect"], "minimax" in _mig),
      ("@img-1 at dusk", [{"filename": "a.png", "handle": "img-1"}],
       [{"name": "x.safetensors", "strength": 0.5}], "9:16", False))
check("...and another arch's blob only loses the stale block",
      h3i.migrate({**_old, "arch": "krea2", "prompt": "keep"}),
      {"arch": "krea2", "prompt": "keep"})
check("...and a blob with nothing to migrate is returned as it is",
      h3i.migrate({"arch": "minimax", "prompt": "x"}), {"arch": "minimax", "prompt": "x"})
_plan = h3i.compile_still(_old, lambda name: (1000, 1500))
check("the migrated blob compiles, its picture cited the MiniMax way",
      (_plan.prompt, _plan.refs, _plan.width, _plan.height),
      ("<Picture 1> at dusk", ["a.png"], 2048, 3648))

# A mask is an inpaint over Picture 1: it makes Picture 1 the edited picture
# and the canvas, and it needs Picture 1 to be there.
_masked = h3i.compile_still({"arch": "minimax", "prompt": "a red door", "refs": [
    {"handle": "img-1", "filename": "door.png"},
    {"handle": "img-2", "filename": "door-matte.png", "role": "guide"}]},
    lambda name: (3000, 2000))
check("a mask lifts off the pictures and makes Picture 1 the edited one",
      (_masked.refs, _masked.control["filename"], _masked.init["filename"],
       (_masked.width, _masked.height)),
      (["door.png"], "door-matte.png", "door.png", (3072, 2048)))
try:
    h3i.compile_still({"arch": "minimax", "prompt": "x", "refs": [
        {"handle": "img-1", "filename": "m.png", "role": "guide"}]})
    FAILURES.append("a mask with no picture under it was not refused")
except _pkg.compile.CompileError as exc:
    check("a mask with no picture under it is refused by name",
          "Picture 1" in str(exc), True)

# ---- MOSS-Image -------------------------------------------------------------

moss = manifest.describe("moss")
mwidgets = {w["id"]: w for w in moss["widgets"]}
for name in ("steps", "cfg", "sampler_name", "scheduler"):
    check(f"moss {name} default is the card's row",
          mwidgets[name]["default"], ms.MOSS_BASE[name])
check("moss weight slots are the family's fields — one DiT, no turbo file",
      [w["id"] for w in moss["weights"]], ["model", "clip", "vae"])
check("moss decodes with the Flux 2 VAE and loads its encoder as moss_image",
      (ms.VAE_KIND, ms.CLIP_TYPE), ("flux2", "moss_image"))
check("moss offers no turbo pill and reads no pictures",
      ("turbo" in moss["capabilities"], "refs" in moss["capabilities"],
       ms.TAKES_REFS, moss["prompt"]["max_refs"]), (False, False, False, 0))
check("moss is a still family on the pill",
      (registry.STILL_ARCHES.get("moss"), "moss" in ci.ARCHES), ("moss", True))


def _header_file(name, keys):
    """A safetensors file that is nothing but a header naming `keys`."""
    import struct
    import tempfile
    body = json.dumps({k: {"dtype": "BF16", "shape": [1], "data_offsets": [0, 0]}
                       for k in keys}).encode()
    path = os.path.join(tempfile.mkdtemp(), name)
    with open(path, "wb") as handle:
        handle.write(struct.pack("<Q", len(body)) + body)
    return path


def _clip_refusal(keys):
    try:
        ms.check_clip(_header_file("te.safetensors", keys), "te.safetensors")
    except ValueError as err:
        return str(err)
    return None


check("moss takes an encoder core detects as Qwen3.5",
      _clip_refusal([ms.QWEN35_KEY, "model.language_model.layers.0.input_layernorm.weight"]), None)
check("...and refuses one saved without the model. prefix, by name",
      "te.safetensors saves its weights without the 'model.' key prefix" in
      (_clip_refusal([ms.QWEN35_KEY_BARE]) or ""), True)
check("...and leaves an encoder it cannot place to the loader",
      _clip_refusal(["text_model.encoder.layers.0.mlp.fc1.weight"]), None)

# ---- MiniMax H3 Still --------------------------------------------------------
#
# The video model drawing one frame: the shared pre-stage blob in, H3's own
# request out, compiled by H3's compiler for its prompt and its refusals.

h3st = manifest.describe("h3still")
h3swidgets = {w["id"]: w for w in h3st["widgets"]}
for name in ("steps", "cfg", "sampler_name", "scheduler"):
    check(f"h3still {name} default is the still row", h3swidgets[name]["default"],
          h3s.H3STILL_ROW[name])
check("h3still is its own arch beside the pill's frozen \"minimax\"",
      (registry.STILL_ARCHES.get("h3still"), registry.STILL_ARCHES.get("minimax"),
       "h3still" in ci.ARCHES, "h3still" in registry.video_families()),
      ("h3still", "h3image", True, False))
check("h3still loads one H3 checkpoint, H3's encoder and the *video* VAE",
      ([w["id"] for w in h3st["weights"]], h3s.VAE_KIND, h3s.CLIP_TYPE),
      (["model", "clip", "vae"], "h3_video", h3slots.CLIP_TYPE))
check("h3still reads as many pictures as H3 does, cited H3's way",
      (h3s.REFS_LIMIT, h3s.REFS_CITATION, h3st["prompt"]["max_refs"]),
      (grammar.of("h3").max_images, "<Picture {n}>", grammar.of("h3").max_images))
check("h3still keeps saved references in H3's space, with no ledger row of its own",
      (registry.REFMOD["h3still"]["space"], registry.REFMOD["h3"]["space"],
       "refmod" in h3st["capabilities"]), ("h3_video", "h3_video", False))
check("h3still's LoRAs go on through H3's stack",
      (registry.LORA_STACK["h3still"], registry.LORA_STACK["h3"]), ("h3lora", "h3lora"))
check("h3still's turbo is a LoRA at the still recipe's strength",
      (h3st["capabilities"]["turbo"]["lora"], h3st["capabilities"]["turbo"]["checkpoint"],
       h3st["capabilities"]["turbo"]["default_strength"], h3s.TURBO_STEPS["good"]),
      (True, False, 0.38, 20))
check("h3still offers no init image and no guide",
      ("init_image" in h3st["capabilities"], "control" in h3st["capabilities"]),
      (False, False))
check("h3still canvas runs to 8 MP on the DiT's /32 grid",
      [ci.resolve_canvas(r, e, ci.canvas_of(h3s)) for r, e in
       ((16 / 9, 1280), (16 / 9, 2176), (1.0, 2176), (9 / 16, 4096))],
      [(2272, 1280), (3872, 2176), (2176, 2176), (2176, 3872)])

_size = lambda name: (1200, 1600)
_still = h3s.compile_still({"arch": "h3still", "prompt": "a red fox in snow",
                            "aspect": "16:9"}, _size)
_seg = h3s.segment_payload(_still)
_shot = _pkg.compile.compile_segment(_seg, _size)
check("a text still is one T2VA generation on the still flow's canvas",
      (_shot.mode, _shot.checkpoint, _shot.width, _shot.height, _shot.frames),
      ("T2VA", "fl2va", 2272, 1280, h3s.REQUEST_FRAMES))
check("...its sentence composed as Context-IR by H3's grammar",
      "integrated_multimodal_description: [Shot 1] a red fox in snow" in _shot.prompt, True)
check("...and the canvas pinned past the video rules' own ceiling",
      _pkg.compile.compile_segment(h3s.segment_payload(h3s.compile_still(
          {"arch": "h3still", "prompt": "x", "short_edge": 2176}, _size)), _size).height,
      2176)

_refd = h3s.compile_still({
    "arch": "h3still", "prompt": "@img-1 beside the car from @img-2, <Picture 7> as typed",
    "refs": [{"handle": "img-1", "filename": "anna.png", "mods": {"h3_video": "refmod:cast/anna"}},
             {"handle": "img-2", "filename": "car.png"}],
    "loras": [{"name": "photo.safetensors", "strength": 1.5, "triggers": ["ph0t0r34l"]},
              {"name": "off.safetensors", "enabled": False}]}, _size)
_req = h3s.request_of(_refd)
check("the pictures become H3 reference assets in slot order",
      [(a["handle"], a["kind"], a["role"], a["filename"]) for a in _req["assets"]],
      [("pic-1", "image", "reference", "anna.png"), ("pic-2", "image", "reference", "car.png")])
check("...a saved reference in H3's space rides on its picture",
      [a.get("mods") for a in _req["assets"]], [{"h3_video": "refmod:cast/anna"}, None])
check("...every citation is handed back to H3's compiler as a handle, a typed one left alone",
      _req["prompt"], "ph0t0r34l, @pic-1 beside the car from @pic-2, <Picture 7> as typed")
check("...and only the LoRAs in the run reach H3's stack, by name and strength",
      _req["loras"], [{"name": "photo.safetensors", "strength": 1.5}])
_refshot = _pkg.compile.compile_segment(h3s.segment_payload(_refd), _size)
check("a still with pictures is a reference generation, each picture defined",
      (_refshot.mode, [a.handle for a in _refshot.ref_images],
       "<Picture 2> is a reference picture" in _refshot.prompt,
       "<Picture 1> beside the car from <Picture 2>" in _refshot.prompt),
      ("REF2VA", ["pic-1", "pic-2"], True, True))

_edit = h3s.compile_still({"arch": "h3still", "prompt": "make the dress red in @img-1",
                           "edit_first": True,
                           "refs": [{"handle": "img-1", "filename": "anna.png"}]}, _size)
check("edit_first fits the canvas to Picture 1 and still starts from noise",
      (_edit.width, _edit.height, _edit.init["denoise"]), (1280, 1696, 1.0))


def _h3s_refusal(data):
    try:
        h3s.compile_still({"arch": "h3still", "prompt": "x", **data}, _size)
    except _pkg.compile.CompileError as err:
        return str(err)
    return None


check("an init image at partial denoise is refused, with the way that works",
      _h3s_refusal({"init": {"filename": "a.png", "denoise": 0.5}}), h3s.INIT_REFUSAL)
check("the turbo pill refuses to engage without its LoRA",
      _h3s_refusal({"turbo": {"h3still": {"on": True}}}), h3s.TURBO_NEEDS_LORA)
check("...and engages with one", _h3s_refusal(
    {"turbo": {"h3still": {"on": True, "lora": "minimax_h3_turbo_v4_step600_ema.safetensors"}}}),
    None)
check("a tenth picture is refused in the family's words",
      h3s.REFS_LIMIT_REASON in (_h3s_refusal(
          {"refs": [{"filename": f"{n}.png"} for n in range(10)]}) or ""), True)

passed("the registry serves every family and the manifests hold their sources")
