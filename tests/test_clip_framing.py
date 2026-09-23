"""A supplied card's crop/turn/mirror survives the UI blob and compilation.

    python tests/test_clip_framing.py

The clip branch has its own parser and serializer; asset framing regressions
do not exercise it. Use both the editor's assignment and a saved blob as inputs.
"""

from pathlib import Path

import layout
from harness import check, FAILURES, passed

layout.skip_without_node()
compiler = layout.load("canvas", "contextir", "compile").compile
passed("all clip framing tests passed")

SCRIPT = """
const S = await import(process.argv[1]);
const crops = [
  { x: 0, y: 0, w: 0.5, h: 1, turn: 90, mirror: "h" },
  { turn: 270 }, { mirror: "v" }, null,
];
const rows = [];
for (const family of ["h3", "ltx25"]) for (const crop of crops) {
  const data = { version: 2, family, render: "chained", segments: [
    { kind: "clip", filename: "footage.mp4", duration_s: 3, width: 640, height: 320 },
    { prompt: "a person", duration_s: 5 },
  ] };
  const edited = S.parseTimeline(JSON.stringify(data));
  if (crop) edited.segments[0].crop = { ...crop };
  const saved = JSON.parse(S.serializeTimeline(edited));
  if (crop) data.segments[0].crop = { ...crop };
  const loaded = S.parseTimeline(JSON.stringify(data));
  const twice = JSON.parse(S.serializeTimeline(S.parseTimeline(JSON.stringify(saved))));
  rows.push({family, crop, saved, loaded: loaded.segments[0], twice,
    size: S.clipSize(loaded.segments[0])});
}
const invalid = S.parseTimeline(JSON.stringify({ version: 2, family: "h3", segments: [
  { kind: "clip", filename: "footage.mp4", duration_s: 3, crop: { turn: 45 } }
] }));
console.log(JSON.stringify({ rows, invalid: JSON.parse(S.serializeTimeline(invalid)) }));
"""

got = layout.run(SCRIPT, Path(layout.js("state.js")).as_uri())
for row in got["rows"]:
    label = f"{row['family']} {row['crop']}"
    crop = row["crop"]
    check(f"{label}: editor writes framing", row["saved"]["segments"][0].get("crop"), crop)
    check(f"{label}: saved framing is restored", row["loaded"].get("crop"), crop)
    check(f"{label}: second round trip is stable", row["twice"], row["saved"])
    spec = compiler.timeline_payloads(row["saved"])[0]["clip"]
    check(f"{label}: compiler receives framing", spec.get("crop"), crop)
    if crop and crop.get("w") == 0.5:
        check(f"{label}: cropped source dimensions", (spec["source_width"], spec["source_height"]), (160, 640))
        check(f"{label}: UI uses cropped dimensions", row["size"], {"width": 160, "height": 640})
    if crop is None:
        check(f"{label}: unframed cards grow no crop", "crop" in row["saved"]["segments"][0], False)

# The existing backend crop parser remains authoritative: preserving a malformed
# crop must not silently turn it into an unframed render.
try:
    compiler.timeline_payloads(got["invalid"])
except compiler.CompileError:
    pass
else:
    FAILURES.append("invalid clip framing was not refused")
