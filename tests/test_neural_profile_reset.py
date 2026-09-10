"""Every neural dial resets to the active profile, not the standard profile.

    python3 tests/test_neural_profile_reset.py
"""

import layout
from domshim import DOM
from harness import check

layout.skip_without_node()

SCRIPT = r'''
import assert from "node:assert/strict";
globalThis.app = { extensionManager: { setting: { get: () => "en" } } };
const S = await import("./web/creator/state.js");
const { neuralRail } = await import("./web/creator/neural.js");
let cases = 0;
for (const profile of S.NEURAL_PROFILES) {
  const block = S.parseNeural({ on: true, profile, detail: 2, colour: 2, intensity: 0.5, scale: 2 });
  const root = document.createElement("div");
  root.replaceChildren(...neuralRail({ block, ranges: S.NEURAL_RANGES, still: true, onChange() {} }));
  const defaults = S.neuralDefaultsFor(profile);
  for (const [index, key] of ["detail", "colour", "intensity", "scale"].entries()) {
    const slider = root.querySelectorAll("input")[index];
    for (const fn of slider.listeners.dblclick ?? []) fn({ target: slider, preventDefault() {} });
    assert.equal(block[key], defaults[key], `${profile}: ${key} reset`);
    assert.equal(slider.value, String(defaults[key]));
    cases++;
  }
}
// A rail can stay mounted while its owner adopts a different profile.
const block = S.parseNeural({ on: true, profile: "standard", detail: 3 });
const root = document.createElement("div");
root.replaceChildren(...neuralRail({ block, ranges: S.NEURAL_RANGES, onChange() {} }));
block.profile = "natural";
const slider = root.querySelector("input");
for (const fn of slider.listeners.dblclick ?? []) fn({ target: slider, preventDefault() {} });
assert.equal(block.detail, S.neuralDefaultsFor("natural").detail);
console.log(JSON.stringify({ cases }));
'''

with layout.pack(skip=["atlas"]) as target:
    result = layout.in_pack(DOM + SCRIPT, target)
check("four dials for every neural profile", result["cases"], 16)
