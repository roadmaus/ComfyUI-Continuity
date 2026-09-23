"""Each image-to-3D stage is timed from where the one before it stopped.

    python3 tests/test_lift_timing.py

The cut-out and the camera finish between two progress events, so a clock
started by a stage's own "running" report read 0 s for both. `stageStart`
starts it where the last earlier stage ended, or where the prompt began
executing. Runs the real module. No server.
"""

import layout
from domshim import DOM
from harness import check

layout.skip_without_node()

SCRIPT = r'''
globalThis.app = { extensionManager: { setting: { get: () => "en" } } };
const { stageStart } = await import("./web/creator/lift.js");
console.log(JSON.stringify({
  first: stageStart({}, "cutout", 1000, 5000),
  second: stageStart({ cutout: { start: 1000, end: 1800 } }, "camera", 1000, 5000),
  // A cached stage has no times; the one after starts where the prompt began.
  afterCached: stageStart({}, "structure", 1000, 5000),
  // The latest earlier end, not the nearest stage's (which may be skipped).
  skipped: stageStart({ cutout: { start: 1000, end: 1800 }, camera: { start: 1800, end: 2600 } },
                      "shape", 1000, 5000),
  // Heard from before `execution_start` was: now, as before.
  unstarted: stageStart({}, "cutout", null, 5000),
}));
'''

with layout.pack(skip=["atlas"]) as target:
    r = layout.in_pack(DOM + SCRIPT, target)

check("the first stage starts when the prompt began executing", r["first"], 1000)
check("the next starts where it stopped", r["second"], 1800)
check("after a cached stage, from where the prompt began", r["afterCached"], 1000)
check("past a skipped stage, from the last one that ran", r["skipped"], 2600)
check("before the prompt is heard to start, now", r["unstarted"], 5000)
