"""A queued tool's answer is heard even when it lands before the reply (issue #47).

    python3 tests/test_queue_order.py

`queue.run` posts a job and waits for the `executed` message carrying its
prompt id. The server puts the job on the queue before it answers the POST, so
a job short enough to finish inside the round trip said `executed` before the
listener existed, and the promise never settled. The collector is now armed
before the request goes out and replays what arrived while the reply was on
its way. Both orders are driven here against a stub `api` whose reply is
released by hand.

Skips itself if node is not installed.
"""

import layout

layout.skip_without_node()

from domshim import DOM  # noqa: E402
from harness import check, passed  # noqa: E402

# A stub api whose POST reply is held until the test releases it, and whose
# events are dispatched by hand — the two ends of the race.
API = """
const listeners = {};
globalThis.__say = (type, detail) => {
  for (const fn of [...(listeners[type] ?? [])]) fn({ type, detail });
};
globalThis.__listening = () => Object.values(listeners).reduce((n, l) => n + l.length, 0);
globalThis.__release = null;
export const api = {
  clientId: "test",
  addEventListener(type, fn) { (listeners[type] ??= []).push(fn); },
  removeEventListener(type, fn) {
    listeners[type] = (listeners[type] ?? []).filter((f) => f !== fn);
  },
  apiURL: (u) => u,
  fetchApi(route, options) {
    return new Promise((resolve) => {
      globalThis.__release = (answer, ok = true) =>
        resolve({ ok, status: ok ? 200 : 500, json: async () => answer });
    });
  },
};
"""

CHECK = """
await import("./dom.mjs");
const queue = await import("./web/creator/queue.js");
const tick = () => new Promise((r) => setTimeout(r, 0));
const settled = (p) => Promise.race([p.then((v) => ({ value: v }), (e) => ({ error: e.message })),
                                     tick().then(() => tick()).then(() => ({ pending: true }))]);
// The module listens for the queue's own state at import; what a run leaves
// behind is counted over that.
const baseline = globalThis.__listening();
const leftover = () => globalThis.__listening() - baseline;
const out = {};

// The race: the job finishes before the reply arrives.
{
  const pending = queue.run("/continuity/job", { kind: "plate" });
  await tick();
  globalThis.__say("executed", { prompt_id: "p1", output: { continuity: [42] } });
  globalThis.__say("executed", { prompt_id: "other", output: { continuity: ["not ours"] } });
  globalThis.__release({ prompt_id: "p1" });
  out.early = await settled(pending);
  out.earlyListeners = leftover();
}

// The ordinary order still works.
{
  const pending = queue.run("/continuity/job", { kind: "plate" });
  await tick();
  globalThis.__release({ prompt_id: "p2" });
  await tick();
  globalThis.__say("executed", { prompt_id: "p2", output: { continuity: [7] } });
  out.late = await settled(pending);
}

// Somebody else's job, before and after the reply, settles nothing.
{
  const pending = queue.run("/continuity/job", { kind: "plate" });
  await tick();
  globalThis.__say("executed", { prompt_id: "other", output: { continuity: [1] } });
  globalThis.__release({ prompt_id: "p3" });
  await tick();
  globalThis.__say("executed", { prompt_id: "other", output: { continuity: [1] } });
  out.foreign = await settled(pending);
  globalThis.__say("execution_error", { prompt_id: "p3", exception_message: "boom" });
  out.foreignThenError = await settled(pending);
}

// A refused POST rejects and leaves no listener behind.
{
  const pending = queue.run("/continuity/job", { kind: "plate" });
  await tick();
  globalThis.__release({ error: "no" }, false);
  out.refused = await settled(pending);
  out.refusedListeners = leftover();
}

// An immediate answer never listens at all.
{
  const pending = queue.run("/continuity/refine", { kind: "refine" });
  await tick();
  globalThis.__release({ result: "text" });
  out.immediate = await settled(pending);
  out.immediateListeners = leftover();
}
console.log(JSON.stringify(out));
"""

with layout.pack(skip=["atlas"], extra_stubs={"api.js": API}) as target:
    got = layout.in_pack(CHECK.replace('await import("./dom.mjs");', DOM), target)

check("an answer that lands before the reply is heard", got["early"], {"value": 42})
check("...and every listener comes off", got["earlyListeners"], 0)
check("an answer after the reply is heard as before", got["late"], {"value": 7})
check("somebody else's answer settles nothing", got["foreign"], {"pending": True})
check("...and the job's own error still does", got["foreignThenError"], {"error": "boom"})
check("a refused post rejects", got["refused"], {"error": "no"})
check("...leaving no listener behind", got["refusedListeners"], 0)
check("an immediate answer is handed straight back", got["immediate"], {"value": "text"})
check("...with nothing left listening", got["immediateListeners"], 0)

passed("a queued job's answer is heard whichever side of the reply it lands on")
