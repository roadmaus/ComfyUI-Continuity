"""Posture, resting on the floor, and lining up a continuing join.

    python3 tests/test_staging_posture.py

Spec 3.2-3.4. A piece rests by itself: whichever way up it is, its lowest point
sits at its height off the floor. The staging sentence says the posture, and
says when it changes within the shot. A continuing join whose next shot starts
the camera or a person somewhere else does not line up, says so, and can be
fixed; a new shot after a staged one starts where it ended.

Skips itself if node is not installed.
"""

import layout

layout.skip_without_node()

from harness import check, passed  # noqa: E402

SCRIPT = r"""
const B = await import("./web/creator/blockout.js");
const S = await import("./web/creator/state.js");
const person = (over) => S.setPiece({ kind: "person", x: 0, z: 4, plays: "anna", ...over }, 1);
const out = {};
const r = (v) => Math.round(v * 1000) / 1000;
out.rest = {
  upright: r(B.centreOf(person({}))[1]),
  flat: r(B.centreOf(person({ rx: Math.PI / 2 }))[1]),
  flatLifted: r(B.centreOf(person({ rx: Math.PI / 2, y: 1.4 }))[1]),
  lowest: r(Math.min(...B.cornersOf(person({ rx: Math.PI / 2, ry: 0.7, rz: 0.3 })).map((c) => c[1]))),
};
out.posture = [
  B.postureOf(person({})), B.postureOf(person({ rx: Math.PI / 2 })), B.postureOf(person({ rz: 0.5 })),
  B.postureOf(person({ rx: Math.PI })), B.postureOf(person({ y: 1.4 })), B.postureOf(person({ rx: Math.PI / 2, y: 1.4 })),
];
const cam = { x: 0, y: 1.6, z: 0, yaw: 0, pitch: 0, mm: 32 };
out.lying = B.stagingSentence([person({ rx: Math.PI / 2 })], [cam], 4, cam, { w: 16, h: 9 }, { withMove: false });
out.ends = B.stagingSentence([person({ rx: Math.PI / 2 })], [cam], 4, cam, { w: 16, h: 9 },
  { withMove: false, ends: [person({})] });
out.standing = B.stagingSentence([person({})], [cam], 4, cam, { w: 16, h: 9 }, { withMove: false });

const piece = () => S.parseTimeline(JSON.stringify({
  version: 2, aspect: "16:9", short_edge: 768, prompt: "",
  sets: [{ id: "k", name: "Kitchen", objects: [{ id: 1, kind: "person", x: 0, z: 4, plays: "anna" }, { id: 2, kind: "wall", z: 6 }] }],
  segments: [
    { prompt: "a", duration_s: 4, assets: [], loras: [], set: "k",
      staging: { camera: [{ t: 0, x: 0, y: 1.6, z: 0, yaw: 0, pitch: 0, mm: 32 }, { t: 4, x: 0, y: 1.6, z: 1, yaw: 0.2, pitch: 0, mm: 32 }],
                 people: { 1: [{ t: 0, x: 0, z: 4 }, { t: 4, x: 1, z: 3 }] } } },
    { prompt: "b", duration_s: 4, assets: [], loras: [], set: "k", continue: true, continue_audio: true,
      staging: { camera: [{ t: 0, x: 0, y: 1.6, z: 0, yaw: 0, pitch: 0, mm: 32 }, { t: 4, x: 0, y: 1.6, z: 2, yaw: 0, pitch: 0, mm: 32 }],
                 people: {} } },
    { prompt: "c", duration_s: 4, assets: [], loras: [], set: "k",
      staging: { camera: [{ t: 0, x: 3, y: 1.6, z: 0, yaw: 0, pitch: 0, mm: 32 }], people: {} } },
  ],
}));
{
  const t = piece();
  const gap = B.joinGap(t, 1);
  out.gap = { camera: r(gap.camera), turn: Math.round(gap.turn), who: gap.who.map((w) => [w.piece.id, r(w.metres), w.posture]) };
  out.hardCut = B.joinGap(t, 2);
  B.lineUp(t, 1);
  out.lined = { gap: B.joinGap(t, 1), first: t.segments[1].staging.camera[0], kept: t.segments[1].staging.camera.map((m) => m.t),
                anna: t.segments[1].staging.people[1] };
  const next = B.stagingFrom(t, 2);
  out.next = { set: next.set, camera: next.staging.camera.map((m) => [m.t, r(m.z)]), anna: next.staging.people[1].map((m) => [m.t, m.x, m.z]) };
  out.loose = [B.postureChanges(t, 0)];
  t.segments[0].staging.people[1][1].rx = Math.PI / 2;
  out.loose.push(B.postureChanges(t, 0));
  out.words = B.stagingWords(t, 0);
}
console.log(JSON.stringify(out));
"""

with layout.pack(skip=["atlas"]) as target:
    got = layout.in_pack(SCRIPT, target)

check("a piece rests on its lowest point, whichever way up it is", got["rest"],
      {"upright": 0.875, "flat": 0.175, "flatLifted": 1.575, "lowest": 0})
check("the posture in words", got["posture"],
      ["", "lying on the floor", "leaning", "upside down", "1.4 m off the ground", "lying 1.4 m off the ground"])
check("a lying person is said to be lying", got["lying"], "@anna is lying on the floor at centre in the midground.")
check("...and a change of posture is said at the end", got["ends"],
      "@anna is lying on the floor at centre in the midground; @anna ends standing.")
check("a standing one stands, as before", got["standing"], "@anna stands at centre in the midground.")
check("a continuing join that does not line up says what jumps", got["gap"],
      {"camera": 1.0, "turn": 11, "who": [[1, 1.414, False]]})
check("a hard cut has no join to line up", got["hardCut"], None)
check("lining it up starts the shot where the last one ended, keeping later marks",
      [got["lined"]["gap"], got["lined"]["first"]["z"], got["lined"]["kept"],
       [[m["t"], m["x"], m["z"]] for m in got["lined"]["anna"]]],
      [None, 1, [0, 4], [[0, 1, 3]]])
check("a new shot after a staged one starts where it ended", got["next"],
      {"set": "k", "camera": [[0, 2]], "anna": [[0, 1, 3]]})
check("a change of posture makes Loosely the suggestion", got["loose"], [False, True])
check("the words say it", "@anna ends lying on the floor" in got["words"], True)

passed("posture, resting and lining up a continuing join")
