"""The real Stage keeps workflow and render clocks on the prompt that made them.

No ComfyUI/GPU is needed: timestamped wire events and history responses drive
the actual listeners, with a deterministic browser clock and DOM shim.
"""

import layout

layout.skip_without_node()

from domshim import DOM  # noqa: E402
from harness import check, passed  # noqa: E402

API = """
import { readFileSync } from "node:fs";
const listeners = {};
globalThis.__say = (type, detail) => {
  for (const fn of [...(listeners[type] ?? [])]) fn({ type, detail });
};
globalThis.__history = {};
globalThis.__fetchHistory = null;
globalThis.__requests = [];
export const api = {
  clientId: "test",
  addEventListener(type, fn) { (listeners[type] ??= []).push(fn); },
  removeEventListener(type, fn) { listeners[type] = (listeners[type] ?? []).filter((f) => f !== fn); },
  dispatchEvent(event) { __say(event.type, event.detail); },
  apiURL: (u) => u,
  async fetchApi(url) {
    if (String(url).startsWith("/continuity/families")) {
      return { ok: true, json: async () => JSON.parse(readFileSync(new URL("./families.json", import.meta.url), "utf8")) };
    }
    if (String(url).startsWith("/history/")) {
      __requests.push(url);
      const body = __fetchHistory ? await __fetchHistory(url) : __history;
      return { ok: true, json: async () => body };
    }
    return { ok: true, json: async () => ({}) };
  },
  async getUserData() { return { status: 404, json: async () => null }; },
  async storeUserData() { return { status: 200 }; },
};
"""

CHECK = r"""
await import("./dom.mjs");
const assert = (await import("node:assert/strict")).default;
const { Stage, elapsed } = await import("./web/creator/stage.js");
let now = 0, nextTimer = 0;
const timers = new Map();
Date.now = () => now;
globalThis.setInterval = (fn) => { const id = ++nextTimer; timers.set(id, fn); return id; };
globalThis.clearInterval = (id) => timers.delete(id);
const cases = [];
const stages = new Set();
const make = (id = 7) => { const stage = new Stage({ nodeId: () => id }); stages.add(stage); return stage; };
const close = () => { for (const stage of stages) stage.destroy(); stages.clear(); __history = {}; __fetchHistory = null; };
const say = (type, detail) => __say(type, detail);
const start = (id, timestamp) => say("execution_start", { prompt_id: id, timestamp });
const progress = (id, node = 7, value = 1, max = 20) => say("progress_state", {
  prompt_id: id, nodes: { [`${node}.9`]: { parent_node_id: String(node), node_id: `${node}.9`,
    prompt_id: id, state: "running", value, max } },
});
const output = (name = "studio.mp4") => ({ mmc_video: [{ filename: name, subfolder: "", type: "output" }] });
const save = (id, node = 7, name) => say("executed", { prompt_id: id, display_node: String(node), output: output(name) });
const success = (id, timestamp) => say("execution_success", { prompt_id: id, timestamp });
const timing = (stage) => stage.clockTiming();
const fields = (result) => ({ totalMs: result.totalMs, tookMs: result.tookMs, totalPending: result.totalPending });
const flush = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };
const history = (id, startAt, endAt, name = "studio.mp4", node = 7) => ({ [id]: {
  outputs: { [`${node}.4`]: output(name) }, meta: { [`${node}.4`]: { display_node: String(node) } },
  status: { status_str: "success", completed: true, messages: [
    ["execution_start", { prompt_id: id, timestamp: startAt }],
    ["execution_success", { prompt_id: id, timestamp: endAt }],
  ] },
} });

// Queue wait is not timing. Browser and server wall clocks intentionally differ.
{
  const stage = make();
  now = 90000;
  assert.deepEqual(timing(stage), { totalMs: null, tookMs: null, totalPending: false });
  start("normal", 1000000);
  now = 95000; progress("normal", 7, 1, 1); // loader: does not open/render-time
  assert.equal(stage.state, "idle");
  now = 97000; progress("normal");
  now = 100000;
  assert.deepEqual(timing(stage), { totalMs: 10000, tookMs: 3000, totalPending: true });
  now = 110000; save("normal");
  const saved = stage.result, media = stage.media.firstChild;
  assert.equal(saved.promptId, "normal");
  assert.deepEqual(fields(saved), { totalMs: 20000, tookMs: 13000, totalPending: true });
  now = 115000; stage.tick();
  assert.deepEqual(timing(stage), { totalMs: 25000, tookMs: 13000, totalPending: true });
  assert.equal(stage.media.firstChild, media, "clock ticks must not rebuild the video");
  success("normal", 1040000); // server duration wins over 25s browser delivery interval
  assert.deepEqual(fields(saved), { totalMs: 40000, tookMs: 13000, totalPending: false });
  assert.equal(stage.result, saved);
  assert.equal(stage.media.firstChild, media);
  assert.equal(timers.size, 0);
  cases.push("queue wait excluded; loaders/downstream included; separate save boundary; stable player");
  close(); await flush();
}

// Two stages in one prompt have one execution clock and separate render windows.
{
  const first = make(7), second = make(9);
  now = 0; start("shared", 5000);
  now = 1000; progress("shared", 7);
  now = 3000; progress("shared", 9);
  now = 5000; save("shared", 7, "first.mp4");
  now = 8000; save("shared", 9, "second.mp4");
  now = 10000; success("shared", 15000);
  assert.deepEqual(timing(first), { totalMs: 10000, tookMs: 4000, totalPending: false });
  assert.deepEqual(timing(second), { totalMs: 10000, tookMs: 5000, totalPending: false });
  cases.push("multiple stages share prompt total, not render duration; zero-origin clock works");
  close(); await flush();
}

// Another queue must leave the previous result and its own clock untouched.
{
  const stage = make();
  now = 100; start("kept", 1000); progress("kept");
  now = 1100; save("kept");
  const kept = stage.result;
  start("foreign", 3000);
  progress("foreign", 9);
  success("foreign", 5000);
  assert.equal(stage.result, kept);
  assert.equal(kept.totalPending, true);
  now = 2100; success("kept", 4000);
  assert.equal(stage.result, kept);
  assert.equal(kept.totalMs, 3000);
  assert.equal(kept.tookMs, 1000);
  start("next", 6000);
  now = 2200; progress("next");
  now = 3200; save("next", 7, "next.mp4");
  const next = stage.result;
  save("kept", 7, "stale.mp4");
  progress("kept");
  say("execution_error", { prompt_id: "kept", node_id: "7.2", exception_message: "late" });
  say("execution_interrupted", { prompt_id: "kept" });
  assert.equal(stage.result, next);
  assert.equal(kept.totalMs, 3000, "a shelf object retains its own finalized timing");
  cases.push("foreign queue and late old prompt events preserve shown/shelved results");
  close(); await flush();
}

// A shelved object still finalizes even when the stage has begun its successor.
{
  const stage = make();
  now = 1000; start("shelf", 10000); progress("shelf");
  now = 2000; save("shelf"); const shelf = stage.result;
  now = 3000; start("replacement", 13000); progress("replacement");
  success("shelf", 12000);
  assert.equal(stage.state, "sampling");
  assert.equal(stage.renderPromptId, "replacement");
  assert.deepEqual(fields(shelf), { totalMs: 2000, tookMs: 1000, totalPending: false });
  cases.push("retired result object updates without replacing a newer running stage");
  close(); await flush();
}

// Cached save has no observed render window; duplicate save must not restart it.
{
  const stage = make();
  now = 1000; start("rendered", 1000); progress("rendered");
  now = 4000; save("rendered"); success("rendered", 4000);
  now = 5000; start("cached", 5000);
  now = 6000; save("cached");
  const cached = stage.result;
  assert.equal(cached.tookMs, null);
  now = 7000; save("cached");
  assert.equal(stage.result, cached);
  success("cached", 6000);
  assert.deepEqual(timing(stage), { totalMs: 1000, tookMs: null, totalPending: false });
  now = 0; start("zero", 0); progress("zero"); save("zero"); success("zero", 0);
  assert.deepEqual(timing(stage), { totalMs: 0, tookMs: 0, totalPending: false });
  cases.push("cached and duplicate results never reuse previous render start; real zero differs from unknown");
  close(); await flush();
}

// Missing start can be recovered from authoritative history, including a tab
// opened mid-render. Recovery never counts the browser's offline time as render.
{
  const stage = make();
  now = 90000; progress("missed-start");
  assert.deepEqual(timing(stage), { totalMs: null, tookMs: 0, totalPending: true });
  __history = history("missed-start", 1000, 9000);
  now = 999000;
  say("reconnected"); await flush();
  assert.equal(stage.state, "done");
  assert.deepEqual(timing(stage), { totalMs: 8000, tookMs: null, totalPending: false });
  cases.push("reconnect without payload recovers server total and file, not fictitious render elapsed");
  close(); await flush();
}

// Save received, then socket lost before downstream completion: update only clocks.
{
  const stage = make();
  now = 100; start("lost-end", 10000); progress("lost-end");
  now = 2100; save("lost-end"); const saved = stage.result, player = stage.media.firstChild;
  __history = history("lost-end", 10000, 18000);
  now = 90000; say("status", {}); await flush();
  assert.equal(stage.result, saved);
  assert.equal(stage.media.firstChild, player);
  assert.deepEqual(fields(saved), { totalMs: 8000, tookMs: 2000, totalPending: false });
  cases.push("post-save disconnected completion updates same result without playback reset");
  close(); await flush();
}

// A cache-only run can lose its save while disconnected without ever beginning
// a sampler. Its own executing claim is sufficient, but not a foreign queue.
{
  const stage = make();
  now = 100; start("before-cache", 1000); progress("before-cache");
  now = 1100; save("before-cache"); success("before-cache", 2000);
  const before = stage.result;
  start("foreign-cache", 3000); say("executing", "9");
  __history = history("foreign-cache", 3000, 4000, "foreign.mp4", 9);
  say("reconnected"); await flush();
  assert.equal(stage.result, before);
  start("own-cache", 5000); say("executing", "7");
  __history = history("own-cache", 5000, 7000, "cached.mp4");
  say("reconnected"); await flush();
  assert.equal(stage.result.name, "cached.mp4");
  assert.deepEqual(timing(stage), { totalMs: 2000, tookMs: null, totalPending: false });
  cases.push("own cached save recovers without begin; foreign cached result stays foreign");
  close(); await flush();
}

// Preview paths start the same render window once. The KJ previewer's cached
// node id can be foreign; a current own executing claim remains authoritative.
{
  const stage = make();
  now = 1000; start("preview", 10000); say("executing", "7");
  say("kj_preview_override", { node_id: "9.2", step: 0, total: 20 });
  assert.equal(stage.state, "idle", "schedule-only metadata is not a render begin");
  now = 2000;
  say("kj_preview_override", { node_id: "9.2", step: 1, total: 20, image: "AAAA", mime: "video/mp4" });
  assert.equal(stage.frameIsClip, true);
  assert.equal(stage.startedAt, 2000);
  now = 4000;
  say("b_preview_with_metadata", { parentNodeId: "7", nodeId: "7.2", promptId: "preview", blob: new Blob(["frame"]) });
  assert.equal(stage.startedAt, 2000);
  now = 5000; save("preview"); success("preview", 15000);
  assert.deepEqual(timing(stage), { totalMs: 5000, tookMs: 3000, totalPending: false });
  const saved = stage.result;
  say("b_preview_with_metadata", { parentNodeId: "7", promptId: "preview", blob: new Blob(["late"]) });
  assert.equal(stage.result, saved, "a terminal preview does not reopen a completed result");
  cases.push("KJ and core metadata preview retain one render boundary and reject terminal late frames");
  close(); await flush();
}

// Start omitted, and success precedes the history write. executing:null retries
// even if that first GET has not settled yet.
{
  const stage = make();
  now = 500; save("history-race");
  let resolve;
  __fetchHistory = () => new Promise((done) => { resolve = done; });
  success("history-race", 9000);
  say("executing", null);
  __fetchHistory = null;
  __history = history("history-race", 1000, 9000);
  resolve({}); await flush();
  assert.deepEqual(timing(stage), { totalMs: 8000, tookMs: null, totalPending: false });
  cases.push("success/history write race retries on payload-free final executing event");
  close(); await flush();
}

// Old history lacks timestamp data. A duration since browser reconnect would be
// a lie even if execution_start had been observed before it slept.
{
  const stage = make();
  now = 100; start("legacy"); progress("legacy");
  __history = history("legacy", undefined, undefined);
  now = 999900; await stage.probe(undefined, true);
  assert.deepEqual(timing(stage), { totalMs: null, tookMs: null, totalPending: false });
  const local = make(9);
  now = 1000; start("local"); progress("local", 9);
  now = 2000; save("local", 9);
  now = 3500; success("local");
  assert.deepEqual(timing(local), { totalMs: 2500, tookMs: 1000, totalPending: false });
  cases.push("legacy history remains unknown; two observed events allow local-only fallback");
  close(); await flush();
}

// Failed downstream work stops total but does not erase an already saved file.
{
  const stage = make();
  now = 100; start("downstream-error", 1000); progress("downstream-error");
  now = 1100; save("downstream-error"); const saved = stage.result;
  say("execution_error", { prompt_id: "downstream-error", node_id: "22", timestamp: 5000, exception_message: "failed later" });
  assert.equal(stage.result, saved);
  assert.deepEqual(fields(saved), { totalMs: 4000, tookMs: 1000, totalPending: false });
  now = 2100; start("cancelled", 7000); progress("cancelled");
  say("execution_interrupted", { prompt_id: "unrelated", timestamp: 9000 });
  assert.equal(stage.state, "sampling");
  say("execution_interrupted", { prompt_id: "cancelled", timestamp: 10000 });
  assert.equal(stage.state, "idle");
  assert.equal(timers.size, 0);
  cases.push("downstream error preserves saved file; interruption is prompt-scoped and stops ticker");
  close(); await flush();
}

// A response to the old run may finalize its shelf clock, but not replace the
// successor; a destroyed stage must never render when its request resolves.
{
  const stage = make();
  now = 100; start("old-flight", 1000); progress("old-flight");
  let resolve;
  __fetchHistory = () => new Promise((done) => { resolve = done; });
  const pending = stage.probe(undefined, true);
  start("new-flight", 9000); // loaders can be running before any own progress
  resolve(history("old-flight", 1000, 8000)); await pending;
  assert.equal(stage.state, "sampling");
  assert.equal(stage.result, null, "new execution_start alone prevents an old history file from landing");
  assert.equal(stage.promptId, "new-flight");
  progress("new-flight");
  assert.equal(stage.renderPromptId, "new-flight");
  const pending2 = stage.probe(undefined, true);
  stage.destroy(); stages.delete(stage);
  let reads = 0;
  stage.renderReadout = () => { reads++; };
  resolve(history("new-flight", 9000, 15000)); await pending2;
  assert.equal(reads, 0);
  assert.equal(timers.size, 0);
  cases.push("in-flight history cannot replace newer run or render after destroy");
  close(); await flush();
}

// One long-lost/purged prompt must not throttle recovery of a newer one. Each
// request has its own prompt key, including results already retired to a shelf.
{
  const stage = make();
  now = 100; start("purged", 1000); progress("purged");
  now = 1100; save("purged");
  now = 2100; start("recover-new", 3000); progress("recover-new");
  now = 3100; save("recover-new");
  __history = history("recover-new", 3000, 6000);
  __requests.length = 0;
  now = 50000; stage.tick(); await flush();
  assert.ok(__requests.includes("/history/purged"));
  assert.ok(__requests.includes("/history/recover-new"));
  assert.deepEqual(timing(stage), { totalMs: 3000, tookMs: 1000, totalPending: false });
  cases.push("history recovery throttle is per prompt, not blocked by an older missing entry");
  close(); await flush();
}

assert.deepEqual([0, 3599000, 3600000, 43384000, 360005000].map(elapsed),
  ["0:00", "59:59", "1:00:00", "12:03:04", "100:00:05"]);
cases.push("hour formatting preserves 100-hour durations");
console.log(JSON.stringify({ cases, activeTimers: timers.size }));
"""

with layout.pack(skip=["atlas"], extra_stubs={"api.js": API}) as target:
    got = layout.in_pack(CHECK.replace('await import("./dom.mjs");', DOM), target)

check("all event/lifecycle scenarios completed", len(got["cases"]), 15)
check("all stage timers disposed", got["activeTimers"], 0)
passed("stage clocks stay prompt-scoped across save, cache, failure, reconnect and replacement")
