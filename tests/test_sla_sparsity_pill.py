"""The attention pill extends with SLA's sparsity, the way Spectrum's does
with its blend (#78).

    python3 tests/test_sla_sparsity_pill.py

The field is blob-only — the node's widget slots are frozen, so it rides the
H3 manifest like `vdn` does — and the pill reads its range and default from
there. What is held: under 'sla' the stepper is on the row and shows the
manifest's default when the blob is silent; under any other backend it is
not drawn at all, so a stale number cannot look in force.

Skips itself if node is not installed.
"""

import layout
from domshim import DOM
from harness import FAILURES, check, passed

layout.skip_without_node()
passed("the attention pill carries SLA's sparsity under sla and nothing otherwise")

_pkg = layout.load("canvas", "accel", "sampling", "contextir", "compile",
                   "compile_image", "models", "registry", "manifest",
                   "h3image_still", "krea2_still", "ideogram4_still", "grammar",
                   "h3_declare", "h3_models", "h3_grammar", "ltx25_declare",
                   "ltx25_models", "ltx25_sampling")
h3 = _pkg.manifest.describe("h3")
SPARSITY = next(w for w in h3["widgets"] if w["id"] == "sla_sparsity")

CHECK = """
await import("./dom.mjs");
const { samplingBar } = await import("./web/creator/sampling.js");

const [, casesJSON] = process.argv;
const cases = JSON.parse(casesJSON);

const textOf = (node) => {
  const out = [];
  const walk = (n) => {
    if (!n) return;
    if (n.tagName === "SPAN" && !(n.children ?? []).length && n.textContent)
      out.push(String(n.textContent).trim());
    (n.children ?? []).forEach(walk);
  };
  walk(node);
  return out;
};

// H3's row is handwritten and gates each pill on the node widget of that
// name, so the attention combo is given one; the sparsity has none and is
// found off the manifest, which is the point.
const widgets = {
  attention: { name: "attention", value: "default",
               options: { values: ["default", "sage", "kitchen", "sla"] } },
};

const out = {};
for (const [label, blob] of Object.entries(cases)) {
  out[label] = textOf(samplingBar({
    widgets,
    value: (name, fallback) => (name in blob ? blob[name] : fallback),
    set: () => {},
    family: "h3",
  }));
}
console.log(JSON.stringify(out));
"""

CASES = {
    "default": {},
    "kitchen": {"attention": "kitchen", "sla_sparsity": 0.7},
    "sla_silent": {"attention": "sla"},
    "sla_dialled": {"attention": "sla", "sla_sparsity": 0.7},
}

with layout.pack(skip=["atlas"]) as target:
    drawn = layout.in_pack(
        CHECK.replace("await import(\"./dom.mjs\");", DOM), target, CASES)


def says(case, needle):
    return any(text == needle for text in drawn[case])


check("the manifest declares the field under the accelerators, gated on sla",
      (SPARSITY["group"], SPARSITY.get("requires")),
      ("accel", [{"id": "attention", "value": "sla"}]))
check("the range is the pack's", (SPARSITY["min"], SPARSITY["max"]), (0.0, 0.95))
check("no sparsity on the row at the checkpoint's own attention",
      any(t.startswith("sparsity") for t in drawn["default"]), False)
check("...nor under another backend, whatever the blob holds",
      any(t.startswith("sparsity") for t in drawn["kitchen"]), False)
check("under sla the pill extends with the manifest's default",
      says("sla_silent", f"sparsity {SPARSITY['default']:.2f}"), True)
check("...and shows the number the blob holds",
      says("sla_dialled", "sparsity 0.70"), True)
check("the backend segment is still there beside it",
      says("sla_dialled", "attention sla"), True)

if FAILURES:
    raise SystemExit(1)
