"""`state.js`'s pre-stage section still agrees with `compile_image.py`.

Same contract as `test_canvas_mirror.py`: the duplication is deliberate — the
pills resolve the image canvas live and the pills' numbers are the presets —
but it is only safe while the two agree. `compile_image.py` is authoritative.

    python3 tests/test_prestage_mirror.py

Skips itself if node is not installed.
"""

import json

import layout

layout.skip_without_node()

MIRROR = layout.js("state.js")

_pkg = layout.load("canvas", "contextir", "compile", "compile_image", "still",
                   "krea2_still", "ideogram4_still", "qwenedit_still",
                   "flux2klein_still")
ci = _pkg.compile_image
cs = _pkg.still
k2 = _pkg.krea2_still
i4 = _pkg.ideogram4_still
qe = _pkg.qwenedit_still
kl = _pkg.flux2klein_still
cv = _pkg.canvas


SCRIPT = """
const s = await import(process.argv[1]);
const out = { constants: {}, canvases: {}, ideogram: {}, turbo: s.PRESTAGE_TURBO_STEPS,
              base_rows: s.PRESTAGE_BASE_ROW, refs: s.PRESTAGE_REFS };
for (const name of ["PRESTAGE_CANVAS_MULTIPLE", "PRESTAGE_MIN_EDGE", "PRESTAGE_MAX_EDGE",
                    "PRESTAGE_DEFAULT_EDGE", "PRESTAGE_MAX_PIXELS", "PRESTAGE_MAX_REFS",
                    "PRESTAGE_DEFAULT_DENOISE", "PRESTAGE_MIN_DENOISE"]) {
  out.constants[name] = s[name];
}
out.max_refs = {
  "krea2": s.preStageMaxRefs({ arch: "krea2" }),
  "qwenedit-2511": s.preStageMaxRefs({ arch: "qwenedit", edition: "2511" }),
  "qwenedit-2509": s.preStageMaxRefs({ arch: "qwenedit", edition: "2509" }),
  "qwenedit-base": s.preStageMaxRefs({ arch: "qwenedit", edition: "base" }),
  "flux2klein": s.preStageMaxRefs({ arch: "flux2klein" }),
};
out.edition_guess = ["Qwen-Image-Edit-2511-fp8.safetensors",
                     "qwen_image_edit_2509_Q4_K_M.gguf",
                     "qwen_image_edit_bf16.safetensors",
                     ""].map((name) => s.preStageEditionGuess(name));
out.reads_guides = {
  "krea2": s.preStageReadsGuides({ arch: "krea2" }),
  "ideogram4": s.preStageReadsGuides({ arch: "ideogram4" }),
  "qwenedit-2511": s.preStageReadsGuides({ arch: "qwenedit", edition: "2511" }),
  "qwenedit-2509": s.preStageReadsGuides({ arch: "qwenedit", edition: "2509" }),
  "qwenedit-base": s.preStageReadsGuides({ arch: "qwenedit", edition: "base" }),
  "flux2klein": s.preStageReadsGuides({ arch: "flux2klein" }),
};
out.arches = [...s.PRESTAGE_ARCHES];
out.image_arches = [...s.PRESTAGE_IMAGE_ARCHES];
out.presets = s.PRESTAGE_ASPECTS.map(([label]) => label).sort();
for (const [label] of s.PRESTAGE_ASPECTS) {
  for (const edge of [512, 768, 1024, 1536, 2048]) {
    const g = s.resolvedPreStage({ aspect: label, short_edge: edge, init: null, refs: [] });
    out.canvases[label + "@" + edge] = [g.width, g.height];
  }
}
for (const quality of s.PRESTAGE_IDEOGRAM_QUALITIES) {
  out.ideogram[quality] = s.PRESTAGE_IDEOGRAM_STEPS[quality];
}
out.still = {
  lengths: [...s.PRESTAGE_STILL_LENGTHS],
  frames: s.PRESTAGE_STILL_FRAMES,
  index: s.PRESTAGE_STILL_INDEX,
  prompt_modes: [...s.PRESTAGE_PROMPT_MODES],
  latents: {},
};
for (const n of s.PRESTAGE_STILL_LENGTHS) out.still.latents[n] = s.stillLatentFrames(n);

// The turbo pill, per arch — and the reading of a blob written before it went
// per arch, which is the migration `compile_image.turbo_block` also does.
out.turbo_arches = Object.keys(s.PRESTAGE_TURBO).sort();
out.turbo_routes = Object.fromEntries(Object.entries(s.PRESTAGE_TURBO)
  .map(([arch, spec]) => [arch, [spec.checkpoint === true, spec.lora === true]]));
out.turbo_steps = Object.fromEntries(Object.entries(s.PRESTAGE_TURBO)
  .map(([arch, spec]) => [arch, spec.steps]));
out.legacy_turbo = s.parsePreStageTurbo({ on: true, quality: "draft" });
out.turbo_needs_lora = s.parsePreStageTurbo({ ideogram4: { on: true } }).ideogram4.on;
out.ref_methods = [...s.PRESTAGE_REF_METHODS];
out.default_ref_method = s.PRESTAGE_DEFAULT_REF_METHOD;
console.log(JSON.stringify(out));
"""

reflected = layout.run(SCRIPT, MIRROR)

from harness import FAILURES, passed


def check(label, got, want):
    if got != want:
        FAILURES.append(f"{label}: state.js says {got!r}, compile_image.py says {want!r}")


PY_CONSTANTS = {
    "PRESTAGE_CANVAS_MULTIPLE": ci.CANVAS_MULTIPLE,
    "PRESTAGE_MIN_EDGE": ci.MIN_SHORT_EDGE,
    "PRESTAGE_MAX_EDGE": ci.MAX_SHORT_EDGE,
    "PRESTAGE_DEFAULT_EDGE": ci.DEFAULT_SHORT_EDGE,
    "PRESTAGE_MAX_PIXELS": ci.MAX_PIXELS,
    "PRESTAGE_MAX_REFS": ci.MAX_STYLE_REFS,
    "PRESTAGE_DEFAULT_DENOISE": ci.DEFAULT_DENOISE,
    "PRESTAGE_MIN_DENOISE": ci.MIN_DENOISE,
}
for name, value in reflected["constants"].items():
    check(name, value, PY_CONSTANTS[name])

# The pill offers the two image architectures `compile_image` owns plus the H3
# branch, which is a video generation and is compiled by `families/h3/still.py`.
check("arches", reflected["arches"], [*ci.ARCHES, cs.ARCH])
check("image arches", reflected["image_arches"], list(ci.ARCHES))
check("still lengths", reflected["still"]["lengths"], list(cs.STILL_LENGTHS))
check("still default length", reflected["still"]["frames"], cs.DEFAULT_FRAMES)
check("still default latent frame", reflected["still"]["index"], cs.DEFAULT_LATENT_INDEX)
check("still prompt modes", reflected["still"]["prompt_modes"], list(cs.PROMPT_MODES))
check("still latent frames", reflected["still"]["latents"],
      {str(n): cs.latent_frames(n) for n in cs.STILL_LENGTHS})
# No canvas check for the H3 branch: its request is an ordinary creator state,
# so the geometry it resolves through is the video nodes' own — which
# `test_canvas_mirror.py` already holds `canvas.js` to.
check("aspect presets", reflected["presets"], sorted(ci.ASPECT_PRESETS))

for key, size in reflected["canvases"].items():
    label, edge = key.split("@")
    check(key, size, list(ci.resolve_canvas(ci.ASPECT_PRESETS[label], int(edge))))

for quality, steps in reflected["ideogram"].items():
    check(f"ideogram {quality} steps", steps, i4.IDEOGRAM_QUALITIES[quality]["steps"])

check("turbo steps", reflected["turbo"], k2.TURBO_STEPS)

# The row each arch arrives on. Written by the arch pill and returned to when
# the turbo switch is released, so a family's own widget defaults are what the
# node ends up sampling at — Krea's 52 at cfg 3.5, Qwen's 20 at cfg 4. Ideogram
# is not here: its steps come off the quality preset, which is checked above.
check("the row each arch arrives on", reflected["base_rows"]["krea2"], k2.KREA_RAW)
check("...and Qwen Image Edit's own", reflected["base_rows"]["qwenedit"], qe.QWEN_BASE)
# Klein declares no scheduler at all — the schedule is Flux2Scheduler's — so
# its arrival row is three values, and the arch pill leaves the widget alone.
check("...and Flux 2 Klein's, scheduler-less", reflected["base_rows"]["flux2klein"],
      kl.KLEIN_BASE)

# What an attached picture means, per arch. Three families, three answers, and
# the pill copy turns on all four of these fields.
check("what a reference is on each arch", reflected["refs"],
      {"krea2": {"reads": True, "methods": list(k2.REF_METHODS),
                 "needsLora": True, "editsFirst": False,
                 "noun": list(k2.REFS_NOUN), "startBlank": None,
                 "nativeControl": [], "controlEditions": [],
                 "adapter": k2.REF_LORA_FIELD,
                 "adapterHints": list(k2.REF_LORA_HINTS),
                 "editions": None, "defaultEdition": None, "editionHints": []},
       "ideogram4": {"reads": False, "methods": [],
                     "needsLora": False, "editsFirst": False,
                     "noun": list(ci.REFS_NOUN), "startBlank": None,
                     "nativeControl": [], "controlEditions": [],
                     "adapter": None, "adapterHints": [],
                     "editions": None, "defaultEdition": None, "editionHints": []},
       "qwenedit": {"reads": True, "methods": [],
                    "needsLora": False, "editsFirst": True,
                    "noun": list(qe.REFS_NOUN),
                    "startBlank": ci.START_BLANK_FIELD,
                    "nativeControl": list(qe.NATIVE_CONTROL),
                    "controlEditions": list(qe.CONTROL_EDITIONS),
                    "adapter": None, "adapterHints": [],
                    "editions": dict(qe.EDITIONS),
                    "defaultEdition": qe.DEFAULT_EDITION,
                    "editionHints": [list(pair) for pair in qe.EDITION_HINTS]},
       "flux2klein": {"reads": True, "methods": [],
                      "needsLora": False, "editsFirst": True,
                      "noun": list(kl.REFS_NOUN),
                      "startBlank": ci.START_BLANK_FIELD,
                      "nativeControl": [], "controlEditions": [],
                      "adapter": None, "adapterHints": [],
                      "editions": None, "defaultEdition": None,
                      "editionHints": []}})

# The cap is the render's, not a constant: the encoder has three image slots on
# every family, and what the checkpoint was post-trained to read is its own
# number — one on the first Qwen-Image-Edit weights. Both halves have to agree,
# or the UI offers a fourth slot the compile will refuse (or refuses a second
# the weights would have read).
check("how many references each render may carry", reflected["max_refs"],
      {"krea2": ci.MAX_STYLE_REFS,
       "qwenedit-2511": qe.EDITIONS["2511"],
       "qwenedit-2509": qe.EDITIONS["2509"],
       "qwenedit-base": qe.EDITIONS["base"],
       "flux2klein": kl.REFS_LIMIT})
check("...and which edition a filename looks like", reflected["edition_guess"],
      ["2511", "2509", None, None])

# Which slot the tracing bench's file lands in is this answer: a picture on the
# editions with the built-in ControlNet, the init image everywhere else. Both
# halves have to agree, or a depth pass goes to the slot that restyles it.
check("which renders read a guide as one of their pictures",
      reflected["reads_guides"],
      {"krea2": False, "ideogram4": False, "flux2klein": False,
       "qwenedit-2511": True, "qwenedit-2509": True, "qwenedit-base": False})

# ---- the turbo pill, per arch ------------------------------------------------
#
# It is one pill and it does not mean one thing: Krea ships the distillation as
# a checkpoint *and* as a LoRA, Ideogram and Qwen Image Edit only as a LoRA.
# Both halves have to agree about which, or the pill offers a route the compiler
# will refuse.

check("every image arch has a turbo pill", reflected["turbo_arches"],
      sorted(ci.ARCHES))
check("which routes each arch offers",
      reflected["turbo_routes"], {"krea2": [True, True], "ideogram4": [False, True],
                                  "qwenedit": [False, True],
                                  "flux2klein": [True, False]})
check("the step ladders are the families' own", reflected["turbo_steps"],
      {"krea2": k2.TURBO_STEPS, "ideogram4": i4.TURBO_STEPS,
       "qwenedit": qe.TURBO_STEPS, "flux2klein": kl.TURBO_STEPS})
check("a blob from before the split reads as Krea 2's",
      (reflected["legacy_turbo"]["krea2"]["on"],
       reflected["legacy_turbo"]["krea2"]["quality"],
       reflected["legacy_turbo"]["ideogram4"]["on"]),
      (True, "draft", False))
check("...and a LoRA-only arch cannot be on without one",
      reflected["turbo_needs_lora"], False)
check("the reference layouts are Krea's own",
      (reflected["ref_methods"], reflected["default_ref_method"]),
      (list(k2.REF_METHODS), k2.DEFAULT_REF_METHOD))

# ---- citing a style reference -----------------------------------------------
#
# The prompt names a reference by handle and the compile turns it into the label
# the encoder itself writes: core's `TextEncodeQwenImageEditPlus` builds
# "Picture 1: <|vision_start|>..." per slot, so `Picture N` is the string the
# model actually reads. Plain, not `<Picture N>` — the brackets are MiniMax H3's
# convention and this is Qwen's.


def still(prompt, refs=(), arch="krea2"):
    # Krea 2 refuses references unless the adapter that reads them is in the
    # stack *and* named — see `test_prestage_graph.py` — so the citations below
    # carry both.
    adapter = "krea2_style_reference.safetensors"
    return {"arch": arch, "prompt": prompt, "width": 1024, "height": 1024,
            "refs": [{"handle": h, "filename": f} for h, f in refs], "models": {},
            "loras": [{"name": adapter, "strength": 1.0}] if refs else [],
            **({"ref_lora": adapter} if refs else {})}


REFS = (("ref-1", "plate.png"), ("ref-2", "coat.png"))

check("a citation becomes the encoder's own label",
      ci.compile_prestage(still("the coat from @ref-2, lit like @ref-1", REFS), k2).prompt,
      "the coat from Picture 2, lit like Picture 1")
check("...numbered by slot, not by handle",
      ci.compile_prestage(still("@ref-2", (("ref-2", "a.png"), ("ref-1", "b.png"))), k2).prompt,
      "Picture 1")
check("the payload still carries filenames in slot order",
      ci.compile_prestage(still("@ref-1 and @ref-2", REFS), k2).refs, ["plate.png", "coat.png"])
check("an uncited reference still rides in as a slot",
      ci.compile_prestage(still("a woman in a red coat", REFS), k2).refs,
      ["plate.png", "coat.png"])
check("ordinary prose is not a citation",
      ci.compile_prestage(still("meet me @ 5 in the courtyard", REFS), k2).prompt,
      "meet me @ 5 in the courtyard")

# A handle naming nothing is an error rather than prose left alone: it means a
# reference was removed and the sentence still points at it.
try:
    ci.compile_prestage(still("lit like @ref-9", REFS), k2)
except ci.CompileError as exc:
    if "@ref-9" not in str(exc):
        FAILURES.append(f"a dangling citation does not name itself: {exc}")
else:
    FAILURES.append("a dangling citation was not refused")

# Ideogram reads no references at all, so it is refused for the reference rather
# than for the citation — one mistake, and the one the user made.
try:
    ci.compile_prestage(still("@ref-1", REFS, arch="ideogram4"), i4)
except ci.CompileError as exc:
    if "Ideogram" not in str(exc):
        FAILURES.append(f"a citation on Ideogram is refused for the wrong reason: {exc}")
else:
    FAILURES.append("style references on Ideogram were not refused")

passed(f"state.js mirrors compile_image.py across {len(reflected['canvases'])} canvases")
