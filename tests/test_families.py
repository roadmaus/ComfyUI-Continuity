"""The registry and the manifests: what exists, and that nothing drifted.

The manifests are built *from* the modules that render — `sampling.DEFAULTS`,
`models.SLOTS`, `canvas.py`, the family packages — so most drift is impossible
by construction. What this suite holds is the part construction cannot: that
every family the registry names actually serves a valid manifest, that the
catalog is JSON (it is a route's whole body), and that the derivations really
do land on the source values they claim to.

Runs standalone, no torch and no ComfyUI — the manifests are pure, which is
the property that lets the frontend's mirror suites read them later.
"""

import json

import layout
from harness import FAILURES, check, passed

_pkg = layout.load("canvas", "accel", "sampling", "contextir", "compile",
                   "compile_image", "models", "registry", "manifest",
                   "still", "krea2_still", "ideogram4_still")
canvas = _pkg.canvas
sampling = _pkg.sampling
models = _pkg.models
registry = _pkg.registry
manifest = _pkg.manifest
ci = _pkg.compile_image
h3s = _pkg.still
k2 = _pkg.krea2_still
i4 = _pkg.ideogram4_still

catalog = manifest.catalog()

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
      [w["id"] for w in h3["weights"]], list(models.SLOTS))
for entry in h3["weights"]:
    slot = models.SLOTS[entry["id"]]
    check(f"h3 slot {entry['id']} mirrors the table",
          (entry["folder"], entry["label"], entry["loads"],
           entry["routed"], entry["audio"]),
          (slot.folder, slot.label, bool(slot.loader),
           slot.routed, slot.audio))

check("h3 routes are models.ROUTES",
      (h3["routes"]["options"], h3["routes"]["default"]),
      (models.ROUTES, models.DEFAULT_ROUTE))

# The derivation targets are routed slots, and the mode names are compile.py's
# own vocabulary — the frontend shows exactly what the compiler will say.
for key in ("reference", "plain", "timeline"):
    check(f"h3 routes[{key}] is a routed slot",
          h3["routes"][key] in models.ROUTED_SLOTS, True)
check("h3 mode names are compile.MODES",
      sorted(set(h3["modes"].values())), sorted(_pkg.compile.MODES))

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
legal = canvas.legal_frame_counts()
check("the manifest's frame grid generates the legal counts",
      [frames["offset"], legal[1] - legal[0]],
      [legal[0], frames["step"]])
check("h3 canvas carries the trained range and the snap",
      (h3["canvas"]["multiple"], frames["trained_min"], frames["trained_max"],
       h3["canvas"]["fps"]),
      (canvas.CANVAS_MULTIPLE, canvas.TRAINED_MIN_FRAMES,
       canvas.TRAINED_MAX_FRAMES, {"value": canvas.FPS, "fixed": True}))
check("h3 aspects are the presets", h3["canvas"]["aspects"],
      canvas.ASPECT_PRESETS)
check("h3 still block is families/h3/still.py's",
      (h3["still"]["arch"], h3["still"]["lengths"],
       h3["still"]["prompt_modes"]),
      (h3s.ARCH, list(h3s.STILL_LENGTHS), list(h3s.PROMPT_MODES)))

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
