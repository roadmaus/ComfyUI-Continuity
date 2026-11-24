"""Put together is offered until the piece's film is the piece as it stands.

    python3 tests/test_put_together.py

Opens the real timeline window and the blockout bench on a piece whose takes are
all kept, reports a finished film of it, and reads the header back.

Skips itself if node is not installed.
"""

import json

import layout

layout.skip_without_node()

from domshim import DOM  # noqa: E402
from harness import check, passed  # noqa: E402

SCRIPT = r'''
process.on("unhandledRejection", (error) => { console.error(error.stack); process.exit(1); });
NodeClass.prototype.getContext = () => ({ createImageData: (w, h) => ({ data: new Uint8ClampedArray(w * h * 4) }),
  putImageData() {}, clearRect() {}, drawImage() {} });
globalThis.app = { graph: { _nodes: [] }, extensionManager: { setting: { get() {} } } };
const S = await import("./web/creator/state.js");
const { TimelineBody } = await import("./web/creator/timeline.js");
const take = (n) => ({ filename: `t${n}.mp4 [output]`, duration_s: 4, has_audio: true });
let raw = JSON.stringify({ version: 2, render: "chained",
  sets: [{ id: "s1", name: "Room", objects: [{ id: 1, kind: "block", x: 0, z: 4 }] }],
  segments: [1, 2].map((n) => ({ prompt: `shot ${n}`, duration_s: 4, assets: [], loras: [], card_id: `c${n}`,
    hold: true, take: take(n), set: "s1",
    staging: { camera: [{ t: 0, x: 0, y: 1.6, z: 0, yaw: 0, pitch: 0, mm: 32 }] } })) });
const body = new TimelineBody({ read: () => raw, write: (next) => { raw = next; }, nodeId: () => 1 });
const text = (node) => (node.textContent ?? "") + (node.children ?? []).map(text).join("");
const head = () => [body.reel.planEl.children.map(text).join(""), body.reel.shootButton.hidden === true];
const film = (id) => {
  body.rememberQueued(id, body.submittedCards({ 1: { inputs: { creator_data: raw } } }));
  return () => body.stage.finish({ mmc_video: [{ filename: "p.mp4", subfolder: "", type: "output" }] }, { promptId: id });
};
const out = {};
body.open();
out.before = head();
film("p1")();
out.after = head();
body.reel.moveTo(1, 0);
out.moved = head();
body.reel.step(body.reel.done, body.reel.undone);
out.undone = head();
const late = film("p2");
body.reel.moveTo(1, 0);
late();
out.changedMeanwhile = head();
body.reel.step(body.reel.done, body.reel.undone);
body.reel.close();
await null;
body.openBlockout();
out.bench = head();
out.reloaded = S.isPutTogether(S.parseTimeline(raw));
console.log(JSON.stringify(out));
process.exit(0);
'''

with layout.pack(skip=["atlas"]) as target:
    got = layout.in_pack(DOM + SCRIPT, target)
got = json.loads(got) if isinstance(got, str) else got
want = ["The piece is put together.", True]
offer = ["Every shot is kept. The next render puts the piece together.", False]
check("with no film it is offered", got["before"], offer)
check("a film of the piece as it stands takes it away", got["after"], want)
check("moving a shot offers it again", got["moved"][1], False)
check("...and undoing that takes it away", got["undone"], want)
check("a film of a piece changed meanwhile does not count", got["changedMeanwhile"][1], False)
check("the bench says the same", got["bench"], want)
check("a reload keeps it", got["reloaded"], True)

passed("put together is offered only while there is something to put together")
