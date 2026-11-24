"""Sets and staging on the piece: read, written, stamped and released.

    python3 tests/test_staging_format.py

The blockout bench stages a piece on sets. A set is the piece's and is shared
by every shot staged on it; a shot carries its own staging (camera marks, and
marks per person). The reel's rules for kept takes apply unchanged, with these
added (spec 3.1):

- a change to a shot's staging releases that shot and the shots that continue
  from it;
- a change to a set releases every shot staged on it, and no other;
- looking around (a set's free look) releases nothing;
- a piece with no sets stamps exactly as it did before sets existed.

Also: a scene the old bench saved beside a guide reads in as a set and a first
shot, and the backend joins a staged shot's words onto its prose.

Skips itself if node is not installed.
"""

import json

import layout

layout.skip_without_node()

from harness import check, passed  # noqa: E402

MIRROR = layout.js("state.js")

SCRIPT = r"""
const s = await import(process.argv[1]);
const blob = () => ({
  version: 2, render: "chained", prompt: "", aspect: "16:9", short_edge: 768,
  sets: [
    { id: "kitchen", name: "Kitchen", view: { yaw: 0.3, pitch: -0.2, orbit: 10, x: 0, y: 1, z: 1 },
      objects: [{ id: 1, kind: "wall", x: 0, z: 4, w: 7 }, { id: 2, kind: "person", x: 1, z: 2, plays: "anna" }] },
    { id: "street", name: "Street", objects: [{ id: 1, kind: "block", x: 2, z: 3, word: "car" }] },
  ],
  segments: [
    { prompt: "one", duration_s: 5, loras: [], assets: [], set: "kitchen",
      staging: { camera: [{ t: 0, x: 0, y: 1.5, z: -4, yaw: 0, pitch: 0, mm: 28 },
                          { t: 5, x: 0, y: 1.5, z: -2, yaw: 0, pitch: 0, mm: 28 }],
                 people: { 2: [{ t: 0, x: 1, z: 2 }, { t: 5, x: 2, z: 1, rx: 1.5708 }] },
                 words: "@anna stands at centre." } },
    { prompt: "two", duration_s: 4, loras: [], assets: [], set: "kitchen", continue: true,
      staging: { camera: [{ t: 0, x: 0, y: 1.5, z: -2, yaw: 0, pitch: 0, mm: 28 }], hold: "loose", pass: "lines" } },
    { prompt: "three", duration_s: 5, loras: [], assets: [], set: "street",
      staging: { camera: [{ t: 0, x: -3, y: 1.2, z: -2, yaw: 0.5, pitch: 0, mm: 35 }] } },
    { prompt: "four", duration_s: 5, loras: [], assets: [] },
  ],
});
const shot = () => {
  const t = s.parseTimeline(JSON.stringify(blob()));
  const queued = s.queuedCards(t);
  s.attachTakes(t, t.segments.map((_, n) => ({ segment: n + 1, filename: "s" + (n + 1) + ".mp4",
    subfolder: "takes", duration_s: 5, width: 1280, height: 720 })), queued);
  return t;
};
const kept = (t) => t.segments.map((seg) => s.isKept(seg));
const after = (edit) => { const t = shot(); edit(t); s.releaseEdited(t); return kept(t); };
const out = {};

{
  const t = s.parseTimeline(JSON.stringify(blob()));
  const again = s.parseTimeline(s.serializeTimeline(t));
  out.roundTrip = s.serializeTimeline(again) === s.serializeTimeline(t);
  out.staged = t.segments.map((seg) => s.isStaged(t, seg));
  out.passes = t.segments.map((seg) => s.stagingPass(t, seg));
  out.strengths = t.segments.slice(0, 2).map((seg) => s.stagingStrength(seg));
  out.view = again.sets[0].view?.orbit ?? null;
  out.onKitchen = s.shotsOnSet(t, "kitchen");
}
{
  // A set that is not on the piece is no set, and a shot without one has no staging.
  const raw = blob();
  raw.segments[2].set = "nowhere";
  const t = s.parseTimeline(JSON.stringify(raw));
  out.orphan = [t.segments[2].set ?? null, t.segments[2].staging ?? null];
}
out.allKept = kept(shot());
out.cameraMoved = after((t) => { t.segments[0].staging.camera[1].x = 1; });
out.personMoved = after((t) => { t.segments[1].staging.people[2] = [{ t: 0, x: 3, y: 0, z: 1, rx: 0, ry: 0, rz: 0 }]; });
out.holdChanged = after((t) => { delete t.segments[1].staging.hold; });
out.kitchenWall = after((t) => { t.sets[0].objects[0].x = 0.5; });
out.streetRenamed = after((t) => { t.sets[1].name = "Lane"; });
out.lookedAround = after((t) => { t.sets[0].view.yaw = 2; });
out.piecePass = after((t) => { t.staging_pass = "blocks"; });
out.setAdded = after((t) => { t.sets.push({ id: "yard", name: "Yard", objects: [] }); });
{
  // A piece with no sets stamps exactly as it did: the same blob without them.
  const raw = blob();
  delete raw.sets;
  for (const seg of raw.segments) { delete seg.set; delete seg.staging; }
  const plain = s.parseTimeline(JSON.stringify(raw));
  out.plainKeys = Object.keys(JSON.parse(s.serializeTimeline(plain))).filter((k) => /^(sets?|staging(_pass)?)$/.test(k));
  out.plainSegKeys = JSON.parse(s.serializeTimeline(plain)).segments.flatMap((seg) => Object.keys(seg)).filter((k) => /^(sets?|staging(_pass)?)$/.test(k));
}
{
  const t = s.parseTimeline(JSON.stringify(blob()));
  const before = s.stagingStamp(t, 0);
  t.sets[0].view.yaw = 1;
  const looked = s.stagingStamp(t, 0);
  t.segments[0].staging.words = "different words";
  const worded = s.stagingStamp(t, 0);
  t.sets[0].objects[0].z = 5;
  const moved = s.stagingStamp(t, 0);
  out.stamp = { looked: before === looked, worded: before === worded, moved: before === moved,
                unstaged: s.stagingStamp(t, 3), name: /^staged-[0-9a-z]+-depth$/.test(s.stagedGuideName(t, 0)) };
}
{
  const read = s.sceneAsStaging({
    objects: [{ kind: "block", x: 1, z: 2, rot: 0.5, plays: "anna" }, { kind: "wall", w: 6 }, { kind: "spaceship" }],
    marks: [{ x: 0, y: 1.6, z: 0, yaw: 0, pitch: 0, mm: 32 }, { x: 0, y: 1.6, z: 1, yaw: 0, pitch: 0, mm: 32 },
            { x: 0, y: 1.6, z: 2, yaw: 0, pitch: 0, mm: 40 }],
    duration: 6, pass: "lines", aspect: "16:9",
  }, { id: "s1", name: "Saved set" });
  out.scene = { kinds: read.set.objects.map((p) => p.kind), ry: read.set.objects[0].ry,
                times: read.staging.camera.map((m) => m.t), pass: read.staging.pass, duration: read.duration };
}
{
  const t = s.parseTimeline(JSON.stringify(blob()));
  s.attachGuide(t.segments[1], t, { path: "continuity/blockout/staged-x-lines.mp4", op: "lines", strength: 0.6 });
  const back = s.parseTimeline(s.serializeTimeline(t));
  out.guide = [back.segments[1].assets[0].strength, s.isStagedGuide(back.segments[1].assets[0])];
}
{
  // Throwing the guide switch releases the shots that carry a guide, not the rest.
  const t = shot();
  t.segments[1].assets.push({ handle: "vid-1", kind: "video", role: "guide", track: "picture",
                              filename: "continuity/blockout/staged-x-depth.mp4" });
  const queued = s.queuedCards(t);
  s.attachTakes(t, [{ segment: 2, filename: "s2b.mp4", subfolder: "takes", duration_s: 5 }], queued);
  const before = kept(t);
  t.guide = { ...t.guide, on: true };
  s.releaseEdited(t);
  out.switch = [before, kept(t)];
}
console.log(JSON.stringify(out));
"""

got = layout.run(SCRIPT, MIRROR)

check("sets and staging survive a round trip", got["roundTrip"], True)
check("...and a set's free look with them", got["view"], 10)
check("the staged shots are the ones with a set", got["staged"], [True, True, True, False])
check("a shot sends its own pass, or the piece's", got["passes"],
      ["depth", "lines", "depth", "depth"])
check("firm is 1.0 and loose 0.6", got["strengths"], [1.0, 0.6])
check("the shots on a set", got["onKitchen"], [0, 1])
check("a shot naming a set the piece lacks has no staging", got["orphan"], [None, None])
check("every take lands kept", got["allKept"], [True, True, True, True])
check("a camera mark releases its shot and the one continuing from it",
      got["cameraMoved"], [False, False, True, True])
check("a person's marks release only their shot", got["personMoved"], [True, False, True, True])
check("how firmly the guide holds releases its shot", got["holdChanged"], [True, False, True, True])
check("a piece of a set releases every shot on it", got["kitchenWall"], [False, False, True, True])
check("...and renaming the other releases its own", got["streetRenamed"], [True, True, False, True])
check("looking around releases nothing", got["lookedAround"], [True, True, True, True])
check("the piece's pass releases the staged shots that use it",
      got["piecePass"], [False, False, False, True])
check("adding a set nobody uses releases nothing", got["setAdded"], [True, True, True, True])
check("a piece with no sets writes no set keys", [got["plainKeys"], got["plainSegKeys"]], [[], []])
check("the guide's stamp ignores free look and the words, not the set",
      got["stamp"], {"looked": True, "worded": True, "moved": False, "unstaged": None, "name": True})
check("an old saved scene reads in as a set and a first shot", got["scene"],
      {"kinds": ["block", "wall"], "ry": 0.5, "times": [0, 3, 6], "pass": "lines", "duration": 6})
check("the guide switch releases only the shots that carry a guide",
      got["switch"], [[True, True, True, True], [True, False, True, True]])
check("a staged guide keeps its own strength", got["guide"], [0.6, True])

# The backend: the words go after the shot's prose, the marks go nowhere.
compiler = layout.load("canvas", "contextir", "compile").compile
segment = {"prompt": "Anna pours coffee.", "set": "kitchen",
           "staging": {"camera": [], "words": "@anna stands at centre."}}
check("the backend joins the words onto the shot's prose",
      compiler._with_staging(segment, segment["prompt"]),
      "Anna pours coffee.\n@anna stands at centre.")
check("...and leaves an unstaged shot as it was",
      compiler._with_staging({"prompt": "x"}, "x"), "x")
assets = compiler._parse_assets([{"handle": "vid-1", "kind": "video", "role": "guide",
                                   "filename": "continuity/blockout/staged-x-depth.mp4",
                                   "track": "picture", "strength": 0.6}]) \
    if hasattr(compiler, "_parse_assets") else None
if assets is not None:
    check("the guide asset's strength is read", assets[0].strength, 0.6)

passed("sets and staging are read, written, stamped and released by the spec's rules")
