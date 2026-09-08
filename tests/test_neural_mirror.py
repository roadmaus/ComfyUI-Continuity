"""`state.js`'s neural block still agrees with `neural.py`.

    python3 tests/test_neural_mirror.py

The pill clamps a request on the way in and the node clamps it again at queue
time; the pill prints a memory estimate and the node logs one. Both are safe
only while the two sides agree on the ranges, the defaults, the profile and
precision vocabularies, and the extent rule the estimate hangs off.
`neural.py` is authoritative.

Skips itself if node is not installed.
"""

import layout

layout.skip_without_node()

MIRROR = layout.js("state.js")

pkg = layout.load("outputs", "settings", "neural")
neural = pkg.neural

from harness import FAILURES, check

SCRIPT = """
const s = await import(process.argv[1]);
const cases = JSON.parse(process.argv[2]);
const sizes = JSON.parse(process.argv[3]);
const out = {
  profiles: s.NEURAL_PROFILES, precisions: s.NEURAL_PRECISIONS, defaults: s.NEURAL_DEFAULTS,
  ranges: s.NEURAL_RANGES, profileDefaults: s.NEURAL_PROFILE_DEFAULTS,
  openAt: {}, parsed: {}, serialized: {}, extents: {}, gb: {},
  piece: JSON.parse(s.serializeState(s.parseState(JSON.stringify({ version: 2, neural: cases.full })))).neural,
  piece_off: "neural" in JSON.parse(s.serializeState(s.parseState(JSON.stringify({ version: 2 })))),
  timeline: JSON.parse(s.serializeTimeline(s.parseTimeline(JSON.stringify({ neural: cases.full })))).neural,
  prestage: JSON.parse(s.serializePreStage(s.parsePreStage(JSON.stringify({ neural: cases.full })))).neural,
  prestage_off: "neural" in JSON.parse(s.serializePreStage(s.parsePreStage("{}"))),
};
for (const [name, raw] of Object.entries(cases)) {
  out.parsed[name] = s.parseNeural(raw);
  out.serialized[name] = s.serializeNeural(s.parseNeural(raw));
}
for (const name of s.NEURAL_PROFILES) out.openAt[name] = s.neuralDefaultsFor(name);
for (const [w, h, scale, precision] of sizes) {
  const key = `${w}x${h}@${scale}/${precision}`;
  out.extents[key] = s.neuralNetworkExtent(w, h, scale);
  out.gb[key] = s.neuralEstimateGb(w, h, scale, precision);
}
console.log(JSON.stringify(out));
"""

CASES = {
    "full": {"on": True, "profile": "cinematic", "scale": 2, "detail": 1.5, "colour": 0.5,
             "intensity": 0.8, "precision": "fast"},
    "off": {"on": False},
    "empty": {},
    "garbage": "yes",
    "clamped": {"on": True, "profile": "vivid", "scale": 9, "detail": -1, "colour": "lots",
                "intensity": 3, "precision": "int4"},
    "strings": {"on": "true", "scale": "1.5", "detail": "2"},
    "preset only": {"on": True, "profile": "natural"},
}
SIZES = [[256, 256, 1, "reference"], [1920, 1080, 1, "reference"], [1920, 1080, 1, "fast"],
         [640, 360, 2, "reference"], [1024, 576, 1.5, "fast"], [1067, 601, 1, "reference"],
         [3840, 2160, 1, "fast"]]

js = layout.run(SCRIPT, MIRROR, CASES, SIZES)

check("profiles", js["profiles"], list(neural.PROFILES))
check("precisions", js["precisions"], list(neural.PRECISIONS))
check("defaults", js["defaults"], neural.DEFAULTS)
check("ranges", js["ranges"], {
    "scale": {"min": neural.MIN_SCALE, "max": neural.MAX_SCALE, "step": 0.25, "default": neural.DEFAULT_SCALE},
    "detail": {"min": neural.MIN_DETAIL, "max": neural.MAX_DETAIL, "step": 0.25, "default": neural.DEFAULT_DETAIL},
    "colour": {"min": neural.MIN_COLOUR, "max": neural.MAX_COLOUR, "step": 0.25, "default": neural.DEFAULT_COLOUR},
    "intensity": {"min": neural.MIN_INTENSITY, "max": neural.MAX_INTENSITY, "step": 0.05,
                  "default": neural.DEFAULT_INTENSITY},
})

check("profile defaults", js["profileDefaults"],
      {name: dict(row) for name, row in neural.PROFILE_DEFAULTS.items()})
for name in neural.PROFILES:
    check(f"{name} opens at", js["openAt"][name], neural.defaults_for(name))

for name, raw in CASES.items():
    want = neural.Request.of({"neural": raw}).as_dict()
    check(f"{name}: parsed alike", js["parsed"][name], want)
    check(f"{name}: serialized alike",
          js["serialized"][name], {"neural": want} if want["on"] else {})

full = neural.Request.of({"neural": CASES["full"]}).as_dict()
check("a piece round-trips the block", js["piece"], full)
check("a timeline round-trips the block", js["timeline"], full)
check("a pre-stage round-trips the block", js["prestage"], full)
check("a piece that never asked writes no block", js["piece_off"], False)
check("a pre-stage that never asked writes no block", js["prestage_off"], False)

for w, h, scale, precision in SIZES:
    key = f"{w}x{h}@{scale}/{precision}"
    check(f"{key}: network extent", js["extents"][key], list(neural.network_extent(w, h, scale)))
    check(f"{key}: estimate", js["gb"][key], neural.estimate_gb(w, h, scale, precision))


# ---- the preset switch -------------------------------------------------------
#
# `adoptProfileDefaults` lives in `neural.js`, which imports ComfyUI's api, so it
# needs the packed tree rather than a bare import of the mirror.

SWITCH = """
const nm = await import("./web/creator/neural.js");
const s = await import("./web/creator/state.js");
const out = {};
for (const name of s.NEURAL_PROFILES) {
  const untouched = { ...s.neuralDefaultsFor("standard") };
  const moved = { ...s.neuralDefaultsFor("standard"), detail: 3.5 };
  out[name] = [nm.adoptProfileDefaults(untouched, name),
               nm.adoptProfileDefaults(moved, name)];
}
console.log(JSON.stringify(out));
"""

with layout.pack(skip=["atlas"]) as target:
    switched = layout.in_pack(SWITCH, target)

for name in neural.PROFILES:
    untouched, moved = switched[name]
    check(f"{name}: an untouched rail follows the preset", untouched,
          {**neural.defaults_for(name), "on": False})
    check(f"{name}: a moved dial survives the switch", moved["detail"], 3.5)
    check(f"{name}: its untouched neighbours still follow", moved["colour"],
          neural.PROFILE_DEFAULTS[name]["colour"])
