"""The room lands a Director run the way the run's record says it did.

    python tests/test_director_room.py

Python is authoritative here as in every mirror suite. A plan is run through
`director_run.drive` against the replay suite's fake renderer, and every
message the server would put on the socket is recorded. The real room is then
opened (the lifecycle suite's DOM shim and API stub) on a chat holding that
plan, and hears them: a card per clip, each landed into the ledger under the
handle the run reserved, the strip and the plan's render records exactly as
`director_run` wrote them, and the room's one line when the piece is done. A
second chat is opened *after* its run finished, and must land the same
clips from `director/status` alone — the tab that pressed Run is gone, and
so is ComfyUI's history after a restart.

Skips itself if node is missing.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import layout  # noqa: E402
from domshim import DOM  # noqa: E402
from harness import check, passed  # noqa: E402

layout.skip_without_node()
pkg = layout.load("prompting", "chat", "director", "director_calls", "director_run")
director, calls, run_mod = pkg.director, pkg.director_calls, pkg.director_run


def fence(obj):
    return "```json\n" + json.dumps(obj) + "\n```"


REPLIES = [
    fence({"questions": [], "assumptions": []}),
    fence({"title": "Night Train", "seconds": 30, "look": "sodium light"}),
    fence({"beats": [{"text": "@george wakes in the carriage.", "weight": "short"},
                     {"text": "He finds the cab empty.", "weight": "long"}]}),
    fence({"entities": [{"name": "carriage", "kind": "place", "description": "an old carriage"}]}),
    fence({"shots": [{"action": "@george wakes up inside @carriage.", "continues": "new"}]}),
    fence({"shots": [{"action": "@george walks the length of @carriage.", "continues": "pin"},
                     {"action": "@george opens the cab door: nobody.", "continues": "cut"}]}),
]
RAIL = {"still": "krea2", "video": "ltx25", "aspect": "16:9", "max_seconds": 60, "references": True}
replies = list(REPLIES)
plan = calls.plan_piece("a 30 second piece: @george on a night train", RAIL,
                        lambda *_: replies.pop(0), cast=[{"name": "george"}])["plan"]
ledger = []
for row in director.prep_steps(plan):
    plan, mark = director.start(plan, row)
    handle = f"pic-{len(ledger) + 1}"
    ledger.append({"handle": handle, "kind": "still", "aspect": "16:9", "turn": 2,
                   "filename": f"{handle}.png [output]", "text": row})
    plan = director.approve(director.land(plan, row, handle, mark), row)


class Recorder:
    """The replay suite's renderer, recording the socket as the route sends it."""

    def __init__(self, chat):
        self.chat, self.sent, self.n, self.current = chat, [], 0, None

    async def build(self, run, step):
        after = step["action"]["after"]
        handles = [c.get("chat_handle") for c in run["strip"]]
        kept = [{**c, "hold": True} for c in run["strip"][:handles.index(after) + 1]] if after else []
        return {"prompt": {}, "piece": {"family": "ltx25", "aspect": "16:9",
                                        "segments": kept + [{"prompt": step["action"]["prompt"],
                                                             "duration_s": step["action"]["seconds"]}]}}

    async def enqueue(self, _prompt):
        self.n += 1
        return f"{self.chat}-p{self.n}"

    async def wait(self, prompt_id):
        segment = len(self.current["piece"]["segments"])
        return "landed", {"node": {
            "mmc_video": [{"filename": f"{prompt_id}.mp4", "subfolder": "chat", "type": "output"}],
            "mmc_takes": [{"segment": segment, "filename": f"{prompt_id}-take.mp4", "subfolder": "chat",
                           "duration_s": self.current["action"]["seconds"], "width": 1280,
                           "height": 720, "has_audio": True}]}}

    def save(self, _run):
        pass

    def tell(self, kind, run, step):
        if kind == "queued":
            self.current = step
        public = run_mod.public(run)
        self.sent.append({"kind": kind, "chat": run["chat"],
                          "run": {k: v for k, v in public.items() if k != "steps"}, "step": step})

    def stopping(self):
        return False


def ran(chat):
    run = run_mod.begin(chat, plan, ledger=ledger, strip=[], piece={},
                        rail={"aspect": "16:9", "video_family": "ltx25"},
                        base={"piece": {"version": 2, "family": "ltx25"}, "widgets": {"seed": 3}},
                        handles=["clip-1", "clip-2", "clip-3"])
    io = Recorder(chat)
    return asyncio.run(run_mod.drive(run, io)), io.sent


live_run, live_events = ran("live")
late_run, _ = ran("late")


def expected(run):
    return {
        "ledger": [[e["handle"], e["kind"], e["filename"]] for e in run["ledger"] if e["kind"] == "clip"],
        "strip": [[c["chat_handle"], c.get("hold"), c["take"]["filename"], c["take"]["duration_s"]]
                  for c in run["strip"]],
        "renders": {rid: [r["state"], r["handle"], r["fingerprint"]]
                    for rid, r in run["plan"]["renders"].items() if not rid.startswith(("e", "kf."))},
    }


def chat_file(plan_doc):
    return {"turn": 2, "counts": {"pic": len(ledger), "clip": 3, "snd": 0}, "ledger": ledger, "strip": [],
            "messages": [{"role": "user", "text": "a 30 second piece", "turn": 1, "brief": True},
                         {"role": "assistant", "say": "A plan.", "plan": {"doc": plan_doc, "warnings": []}}]}


here = Path(__file__).parent
api = layout.STUBS["api.js"] + (here / "chat_lifecycle_api.mjs").read_text(encoding="utf-8")
script = DOM + """
import assert from "node:assert/strict";
const timers = new Map();
let timerId = 0;
globalThis.setTimeout = (run, after) => { timers.set(++timerId, { run, after }); return timerId; };
globalThis.clearTimeout = id => timers.delete(id);
globalThis.setInterval = () => ++timerId;
globalThis.clearInterval = () => {};
globalThis.matchMedia = () => ({ matches: false });
globalThis.app = { extensionManager: { setting: { get: () => "en" } } };
const { lifecycle } = await import("../scripts/api.js");
const store = await import("./web/creator/chatstore.js");
const { openChat } = await import("./web/creator/chat.js");
const files = globalThis.__userdata;
const drain = async () => { for (let i = 0; i < 100; i++) await Promise.resolve(); };
const one = (selector, root = document.body) => root.querySelector(selector);
async function click(node) {
  for (const handler of node.listeners.click ?? []) {
    await handler({ currentTarget: node, target: node, stopPropagation() {}, preventDefault() {} });
  }
  await drain();
}
async function save() {
  for (const [id, timer] of [...timers]) {
    if (timer.after !== 600) continue;
    timers.delete(id);
    timer.run();
  }
  await drain();
}
const [fixture, events, lateStatus] = process.argv.slice(1).map((arg) => JSON.parse(arg));
for (const id of ["live", "late"]) await store.saveChat({ id, title: id, created: 1 }, fixture);
const response = (body) => ({ ok: true, status: 200, json: async () => body });
lifecycle.http = async (route) => {
  if (route.startsWith("/continuity/director/status?chat=late")) return response({ result: lateStatus });
  if (route.startsWith("/continuity/director/status")) return response({ result: null });
};
const closed = openChat();
await drain();
const read = (id) => {
  const body = JSON.parse(files.get(`continuity.chat.${id}.json`));
  const doc = body.messages.find((m) => m.plan)?.plan.doc;
  return {
    ledger: body.ledger.filter((e) => e.kind === "clip").map((e) => [e.handle, e.kind, e.filename]),
    strip: body.strip.map((c) => [c.chat_handle, c.hold, c.take.filename, c.take.duration_s]),
    renders: Object.fromEntries(Object.entries(doc.renders).filter(([id]) => !/^(e|kf\\.)/.test(id))
      .map(([id, r]) => [id, [r.state, r.handle, r.fingerprint]])),
    cards: body.messages.filter((m) => m.card?.run).map((m) => [m.card.state, m.card.run.handle, m.say]),
    last: body.messages.at(-1).say,
    counts: body.counts,
  };
};
const out = {};
await click(one('.mmc-ch-sideopenbtn', one('.mmc-ch-siderow[data-id="live"]')));
for (const detail of events) lifecycle.emit("mmc_director", detail);
await save();
out.live = read("live");
// Somebody else's chat hears nothing of this run.
lifecycle.emit("mmc_director", { ...events[1], chat: "nobody" });
await click(one(".mmc-ch-new"));
await click(one('.mmc-ch-sideopenbtn', one('.mmc-ch-siderow[data-id="late"]')));
await drain();
await save();
out.late = read("late");
await click(one('[title="Close the room"]'));
await closed;
console.log(JSON.stringify(out));
"""

late_status = run_mod.public(late_run)
with layout.pack(skip=["atlas"], extra_stubs={"api.js": api}) as target:
    got = layout.in_pack(script, target, chat_file(plan), live_events, late_status)

for name, run in (("live", live_run), ("late", late_run)):
    want = expected(run)
    room = got[name]
    where = "heard on the socket" if name == "live" else "caught up from the run file"
    check(f"{where}: the clips join the ledger under the handles the run reserved, citing their takes",
          room["ledger"], want["ledger"])
    check(f"{where}: the strip is the run's, every shot held on its take", room["strip"], want["strip"])
    check(f"{where}: the plan files each clip as the run did, fingerprint and all",
          room["renders"], want["renders"])
    check(f"{where}: a card per clip, landed, saying its shot",
          room["cards"], [["done", "clip-1", "Shot 1, from the plan."],
                          ["done", "clip-2", "Shot 2, from the plan."],
                          ["done", "clip-3", "Shot 3, from the plan."]])
    check(f"{where}: and the room says the piece is done",
          room["last"], "“Night Train” is finished: 30 seconds in 3 shots. The last clip plays the whole piece.")
    check(f"{where}: the clip counter stays past the reserved handles", room["counts"]["clip"], 3)
passed("the room lands a Director run as the run's record says")
