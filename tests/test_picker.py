"""The picker mounts for every kind of caller, including the ones with no slots.

The picker was written for reference buckets, where every pick is priced against
a maximum — nine images, three videos, twelve files. `options.capacity` answered
that, and `renderFoot` read it while mounting, unconditionally. So a caller with
no buckets to report did not get a modal with a missing readout: it got
`TypeError: this.options.capacity is not a function` out of `mount()`, and from
the user's side the button simply did nothing.

That caller now exists. A track on the sound lane is bounded by the length of the
piece, not by a slot, and inventing a bucket for it so the picker had something
to divide by would have been a control pretending to be a limit.

So both modes are mounted here. The bounded one is the ordinary path and the
unbounded one is the regression: it is easy to reach for `capacity` again while
adding a readout, and the failure is total and silent from Python's side.

    python3 tests/test_picker.py

Skips itself if node is not installed.
"""

import domshim
import layout
from harness import check, passed

layout.skip_without_node()

SCRIPT = domshim.DOM + """
import { openPicker } from "./web/creator/picker.js";

const find = (cls, node = document.body) => {
  if (node.className && String(node.className).split(" ").includes(cls)) return node;
  for (const kid of node.children ?? []) {
    const hit = find(cls, kid);
    if (hit) return hit;
  }
  return null;
};

const tabs = () => {
  const found = [];
  const walk = (node) => {
    if (node.className && String(node.className).split(" ").includes("mmc-tab")) {
      found.push(node.textContent);
    }
    for (const kid of node.children ?? []) walk(kid);
  };
  walk(document.body);
  return found;
};

function mount(options) {
  document.body.children.length = 0;
  try {
    openPicker(options);
    return { ok: true, slots: find("mmc-slots")?.textContent ?? null, tabs: tabs() };
  } catch (err) {
    return { ok: false, error: String((err && err.message) || err) };
  }
}

// ...and what the lane does with what comes back. `lay` is `add` without the
// modal, so the placement can be exercised without one: where a second file
// starts, what a trim does to the window, and what happens when the piece runs
// out before the picks do.
async function laid(picks, seconds) {
  const { SoundLane } = await import("./web/creator/soundlane.js");
  const piece = { family: "h3", segments: [{ prompt: "x", duration_s: seconds }] };
  const flashes = [];
  const lane = new SoundLane({
    read: () => piece, onCommit() {}, flash: (m) => flashes.push(m),
  });
  // The probe route does not exist here, so the file lengths are supplied the
  // way the picker's own trim would have.
  for (const pick of picks) lane.lengths.set(pick.path, pick.whole);
  await lane.lay(picks);
  return { sound: piece.sound, flashes };
}

const out = {
  // The sound lane's own call: no capacity, because there are no buckets.
  lane: mount({ kinds: ["audio", "video"], kind: "audio" }),
  // A reference caller, which prices every pick against its buckets.
  bucketed: mount({
    kinds: ["image", "video", "audio"], kind: "image",
    capacity: (kind) => ({ used: kind === "image" ? 2 : 0, max: 9, filesLeft: 10 }),
  }),
  // One pick only — the start/end frame path, which has never read capacity.
  single: mount({ kinds: ["image"], kind: "image", single: true }),
};
// A 12 s piece: two files laid end to end, the second trimmed before it arrived.
out.two = await laid([
  { path: "score.mp3", whole: 5 },
  { path: "vo.wav", whole: 30, trim: { start: 2, end: 6 } },
], 12);
// A 5 s piece and a four-minute album track: cut to what is left rather than
// refused, because that is what dropping one on a short piece means.
out.long = await laid([{ path: "album.flac", whole: 240 }], 5);
// ...and a second file with nowhere to go says so instead of landing at 0.
out.full = await laid([
  { path: "a.wav", whole: 30 },
  { path: "b.wav", whole: 30 },
], 5);
console.log(JSON.stringify(out));
"""

with layout.pack(skip=("atlas",)) as target:
    got = layout.in_pack(SCRIPT, target)

check("a caller with no buckets mounts at all", got["lane"]["ok"], True)
check("...on the tabs it asked for", got["lane"]["tabs"], ["Audio", "Video"])
# The readout counts rather than prices. "0 / Infinity slots filled" is the
# failure this is guarding against as much as the throw is.
check("...and the readout invites a pick instead of naming a maximum",
      got["lane"]["slots"], "Pick as many as you like")

check("a bucketed caller still mounts", got["bucketed"]["ok"], True)
check("...and still prices its picks", got["bucketed"]["slots"], "2 / 9 slots filled")

check("the single-pick caller still mounts", got["single"]["ok"], True)
check("...and still asks for one", got["single"]["slots"], "Pick one")

# ---- and what the lane does with the picks -----------------------------------

two = got["two"]["sound"]
check("two files land end to end", [b["at_s"] for b in two], [0.0, 5.0])
check("...each keeping its own window into its file",
      [[b["in_s"], b["out_s"]] for b in two], [[0.0, 5.0], [2.0, 6.0]])
check("...and neither complains", got["two"]["flashes"], [])

# The cut is the interesting half: the block is the whole of a 5 s piece taken
# out of a 240 s file, so the out point moved and the in point did not.
#
# 5.167 and not 5: a piece is as long as its passes, and a pass is snapped to
# the family's frame grid — H3's nearest legal count to 5 s is 124 frames, which
# is 5.1667 s. The lane fills the piece it is actually on, not the one the
# duration pill rounds to.
long_ = got["long"]["sound"]
check("a file longer than the piece is cut, not refused", len(long_), 1)
check("...to exactly what the piece runs to",
      [long_[0]["in_s"], long_[0]["out_s"]], [0.0, round(124 / 24, 3)])

check("a file with nowhere to go is not laid", len(got["full"]["sound"]), 1)
check("...and says why", len(got["full"]["flashes"]), 1)
check("...naming the file it could not place",
      "b.wav" in (got["full"]["flashes"][0] or ""), True)

passed("the picker mounts bounded, unbounded and single, and the lane lays what comes back")
