"""`state.js`'s pre-stage section still agrees with `compile_image.py`.

Same contract as `test_canvas_mirror.py`: the duplication is deliberate — the
pills resolve the image canvas live and the pills' numbers are the presets —
but it is only safe while the two agree. `compile_image.py` is authoritative.

    python3 tests/test_prestage_mirror.py

Skips itself if node is not installed.
"""

import json

import mirror

mirror.skip_without_node()

MIRROR = mirror.js("state.js")

_pkg = mirror.load("canvas", "contextir", "compile", "compile_image", "compile_still")
ci = _pkg.compile_image
cs = _pkg.compile_still
cv = _pkg.canvas


SCRIPT = """
const s = await import(process.argv[1]);
const out = { constants: {}, canvases: {}, ideogram: {}, turbo: s.PRESTAGE_TURBO_STEPS,
              krea_raw: s.PRESTAGE_KREA_RAW };
for (const name of ["PRESTAGE_CANVAS_MULTIPLE", "PRESTAGE_MIN_EDGE", "PRESTAGE_MAX_EDGE",
                    "PRESTAGE_DEFAULT_EDGE", "PRESTAGE_MAX_PIXELS", "PRESTAGE_MAX_REFS",
                    "PRESTAGE_DEFAULT_DENOISE", "PRESTAGE_MIN_DENOISE"]) {
  out.constants[name] = s[name];
}
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
console.log(JSON.stringify(out));
"""

reflected = mirror.run(SCRIPT, MIRROR)

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
# branch, which is a video generation and is compiled by `compile_still`.
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
    check(f"ideogram {quality} steps", steps, ci.IDEOGRAM_QUALITIES[quality]["steps"])

check("turbo steps", reflected["turbo"], ci.TURBO_STEPS)
check("krea RAW row", reflected["krea_raw"], ci.KREA_RAW)

# ---- citing a style reference -----------------------------------------------
#
# The prompt names a reference by handle and the compile turns it into the label
# the encoder itself writes: core's `TextEncodeQwenImageEditPlus` builds
# "Picture 1: <|vision_start|>..." per slot, so `Picture N` is the string the
# model actually reads. Plain, not `<Picture N>` — the brackets are MiniMax H3's
# convention and this is Qwen's.


def still(prompt, refs=(), arch="krea2"):
    return {"arch": arch, "prompt": prompt, "width": 1024, "height": 1024,
            "refs": [{"handle": h, "filename": f} for h, f in refs], "models": {}}


REFS = (("ref-1", "plate.png"), ("ref-2", "coat.png"))

check("a citation becomes the encoder's own label",
      ci.compile_prestage(still("the coat from @ref-2, lit like @ref-1", REFS)).prompt,
      "the coat from Picture 2, lit like Picture 1")
check("...numbered by slot, not by handle",
      ci.compile_prestage(still("@ref-2", (("ref-2", "a.png"), ("ref-1", "b.png")))).prompt,
      "Picture 1")
check("the payload still carries filenames in slot order",
      ci.compile_prestage(still("@ref-1 and @ref-2", REFS)).refs, ["plate.png", "coat.png"])
check("an uncited reference still rides in as a slot",
      ci.compile_prestage(still("a woman in a red coat", REFS)).refs,
      ["plate.png", "coat.png"])
check("ordinary prose is not a citation",
      ci.compile_prestage(still("meet me @ 5 in the courtyard", REFS)).prompt,
      "meet me @ 5 in the courtyard")

# A handle naming nothing is an error rather than prose left alone: it means a
# reference was removed and the sentence still points at it.
try:
    ci.compile_prestage(still("lit like @ref-9", REFS))
except ci.CompileError as exc:
    if "@ref-9" not in str(exc):
        FAILURES.append(f"a dangling citation does not name itself: {exc}")
else:
    FAILURES.append("a dangling citation was not refused")

# Ideogram reads no references at all, so it is refused for the reference rather
# than for the citation — one mistake, and the one the user made.
try:
    ci.compile_prestage(still("@ref-1", REFS, arch="ideogram4"))
except ci.CompileError as exc:
    if "Ideogram" not in str(exc):
        FAILURES.append(f"a citation on Ideogram is refused for the wrong reason: {exc}")
else:
    FAILURES.append("style references on Ideogram were not refused")

passed(f"state.js mirrors compile_image.py across {len(reflected['canvases'])} canvases")
