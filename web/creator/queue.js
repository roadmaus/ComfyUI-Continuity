// What the queue is doing, in one place, for everything that needs to know.
//
// There was no such place. `fullscreen.js` kept its own `status` listener and
// its own count, `stage.js` listened to the same event for its own reasons, and
// every bench and the refine pill tracked a private `busy` flag that knew only
// about its own request in flight. So nothing on the page could say the one
// thing that matters now that this pack's work is queued (`creator/jobs.py`):
// *something else has the GPU*.
//
// Two things live here. `watch` is that shared state — how many are on the
// queue, whether one is running — pushed to whoever asked. `run` is the other
// half: post a job, and resolve when the queue has finished it.

import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";
import { t } from "./i18n.js";

/** Queue one node, as pressing its Render does. A bare array for the target —
 *  see `fullscreen.queue` for why not `{queueNodeIds}`. */
export function queueNode(nodeId) {
  return app.queuePrompt(0, 1, [String(nodeId)]).catch(() => {});
}

const listeners = new Set();

// promptQueued is a batch notification ({number, batchCount, requestId}) in
// ComfyUI's frontend, not a server prompt id. Observe the actual submission
// boundary once so each accepted prompt is paired with the graph it sent,
// including batches and replies that arrive after an execution event.
const submissions = new Set();

// What each accepted prompt was made of — the node ids and titles of the graph
// that went out, and which nodes the press named. Kept so a stage hearing an
// `execution_error` for some node it did not emit — a loader wired in upstream,
// the other half of a pre-stage pair — can still tell whether the run that
// broke was the run its Render started. Bounded: a tab that queues all day
// must not remember all day.
const submitted = new Map();
const REMEMBERED = 64;

/** The name each node in a submitted graph goes by — what the user called it,
 *  else what it is. `_meta.title` is the frontend's own stamp on every node. */
function titlesOf(output) {
  const titles = {};
  for (const [id, node] of Object.entries(output ?? {})) {
    titles[id] = node?._meta?.title || node?.class_type || id;
  }
  return titles;
}

function remember(promptId, output, targets) {
  submitted.set(promptId, { titles: titlesOf(output), targets });
  while (submitted.size > REMEMBERED) submitted.delete(submitted.keys().next().value);
}

/** What went out under `promptId`, or null for a prompt this tab did not send:
 *  `{titles: {id: title}, targets: [id]}` — targets empty for a plain queue. */
export function submission(promptId) {
  return submitted.get(String(promptId)) ?? null;
}

// The server's account of a refused prompt, flattened to what a person can
// act on. `node_errors` is keyed by node id with a list of `{message, details}`
// per node; a refusal with no node to blame (`prompt_no_outputs`, an
// unreadable body) comes as `error` alone. ComfyUI's `details` for a bad combo
// value is the whole list of valid ones, which nobody reads off a card.
function refusalItems(response, titles) {
  const items = [];
  const clip = (text) => (text.length > 240 ? `${text.slice(0, 239)}…` : text);
  for (const [id, entry] of Object.entries(response?.node_errors ?? {})) {
    for (const error of entry?.errors ?? []) {
      const what = [error.message, error.details].filter(Boolean).join(": ");
      items.push({ nodeId: id, where: titles[id] ?? entry.class_type ?? id, what: clip(what) });
    }
  }
  const top = response?.error;
  if (!items.length && top) {
    const what = typeof top === "string" ? top
      : [top.message, top.details].filter(Boolean).join(": ");
    items.push({ nodeId: null, where: null, what: clip(what || t("the render was refused")) });
  }
  return items;
}

// The one place every prompt this tab sends goes through. Wrapping the API
// rather than `app.queuePrompt` because that one catches a refusal itself,
// shows what it shows and resolves — and what it shows is, since the errors
// tab arrived (frontend 1.36+, on by default), a tab in a side panel that the
// fullscreen editor stands in front of. So the refusal is caught here on its
// way past and said again on the api as `mmc_refused`, which the stages
// listen for like any other event of the queue's.
if (typeof api.queuePrompt === "function") {
  const original = api.queuePrompt;
  api.queuePrompt = async function (...args) {
    const output = args[1]?.output;
    const targets = (args[2]?.partialExecutionTargets ?? []).map(String);
    const snapshots = [];
    for (const listener of submissions) {
      try {
        const snapshot = listener.capture(output);
        if (snapshot) snapshots.push([listener, snapshot]);
      } catch (error) { console.warn("[Continuity] could not snapshot a submitted strip", error); }
    }
    // Preserve the API's arguments, receiver, result and rejection. A failed
    // request must not create a queue entry or attach somebody else's take.
    let answer;
    try {
      answer = await original.apply(this, args);
    } catch (error) {
      // A refusal has `response`; a wire that is down has only a message.
      const items = refusalItems(error?.response, titlesOf(output));
      if (!items.length) items.push({ nodeId: null, where: null, what: String(error?.message ?? error) });
      api.dispatchEvent(new CustomEvent("mmc_refused", {
        detail: { nodes: Object.keys(output ?? {}), targets, items },
      }));
      throw error;
    }
    if (answer?.prompt_id) {
      remember(String(answer.prompt_id), output, targets);
      for (const [listener, snapshot] of snapshots) {
        if (!submissions.has(listener)) continue;
        try { listener.accepted(String(answer.prompt_id), snapshot); }
        catch (error) { console.warn("[Continuity] could not record a submitted strip", error); }
      }
    }
    return answer;
  };
}

/** Take a job that has not started off the queue. A running one is left to
 *  finish — interrupting is the Cancel button's, and it would hit whatever is
 *  on the sampler, which may be somebody's render. */
export function dropQueued(promptId) {
  return api.fetchApi("/queue", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ delete: [String(promptId)] }),
  }).catch(() => {});
}

/** The server's current state for this prompt, including one restored after
 *  reload before its next progress event. */
export async function promptQueueState(promptId) {
  const response = await api.fetchApi("/queue");
  if (!response.ok) throw new Error(t("Could not read the queue."));
  const queue = await response.json();
  const contains = (rows) => (rows ?? []).some((row) => String(row?.[1]) === String(promptId));
  return contains(queue.queue_running) ? "running" : contains(queue.queue_pending) ? "queued" : null;
}

/** Cancel by prompt identity, never by the card's possibly stale UI state.
 *  A targeted interrupt cannot stop the next job if this one just finished. */
export async function cancelPrompt(promptId) {
  let status = await promptQueueState(promptId);
  if (status === "queued") {
    const response = await api.fetchApi("/queue", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ delete: [String(promptId)] }),
    });
    if (!response.ok) throw new Error(t("Could not cancel the render."));
    status = await promptQueueState(promptId);
    if (status === null) return "removed";
    if (status === "queued") throw new Error(t("The render is still on the queue."));
  }
  if (status === "running") {
    const response = await api.fetchApi("/interrupt", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt_id: String(promptId) }),
    });
    if (!response.ok) throw new Error(t("Could not cancel the render."));
  }
  return status;
}

export function watchSubmittedPrompts(capture, accepted) {
  const listener = { capture, accepted };
  submissions.add(listener);
  return () => submissions.delete(listener);
}

/** Recover the submitted graph after a page reload, never the current graph.
 * A running prompt lives in /queue; a completed/failed one lives in history. */
export async function submittedPrompt(promptId) {
  const id = String(promptId);
  const history = await api.fetchApi(`/history/${encodeURIComponent(id)}`);
  if (history.ok) {
    const entry = (await history.json())?.[id];
    if (entry?.prompt?.[2]) return entry.prompt[2];
  }
  const response = await api.fetchApi("/queue");
  if (!response.ok) return null;
  const queue = await response.json();
  const entry = [...(queue.queue_running ?? []), ...(queue.queue_pending ?? [])]
    .find((item) => String(item?.[1]) === id);
  if (entry?.[2]) return entry[2];
  // The render may have left the queue between those two reads.
  const finished = await api.fetchApi(`/history/${encodeURIComponent(id)}`);
  return finished.ok ? (await finished.json())?.[id]?.prompt?.[2] ?? null : null;
}

// `remaining` is ComfyUI's own `queue_remaining`: everything queued including
// whatever is on the sampler right now. `running` is whether execution has
// actually started on one, which is the difference between "yours is next" and
// "yours is third".
const state = { remaining: 0, running: false };

function announce() {
  for (const listener of listeners) {
    try {
      listener({ ...state });
    } catch (error) {
      // One surface that throws while painting must not stop the others from
      // hearing. It is a bug in that surface, and this is not where it is fixed.
      console.error("[Continuity] a queue listener threw", error);
    }
  }
}

api.addEventListener("status", (event) => {
  const left = event.detail?.exec_info?.queue_remaining;
  if (typeof left !== "number") return;
  state.remaining = left;
  // The queue emptying is the one report that settles `running` on its own:
  // `execution_success` does not fire for an interrupted prompt, and neither
  // does anything else that would clear this.
  if (left === 0) state.running = false;
  announce();
});

for (const [name, running] of [["execution_start", true], ["execution_success", false],
                               ["execution_error", false], ["execution_interrupted", false]]) {
  api.addEventListener(name, () => { state.running = running; announce(); });
}

/** Whether anything at all is on the queue — the question every gated surface
 *  asks, and the same one `jobs.busy()` answers on the server. */
export function busy() {
  return state.remaining > 0 || state.running;
}

/** Current state without subscribing. */
export function queueState() {
  return { ...state };
}

/**
 * Call `listener({remaining, running})` on every change, and once immediately so
 * a surface that mounts mid-render paints correctly rather than as idle.
 *
 * -> an unsubscribe. Every caller is a panel or a node body that gets torn down,
 * and a listener that outlived its DOM is the leak `stage.destroy` exists for.
 */
export function watch(listener) {
  listeners.add(listener);
  listener({ ...state });
  return () => listeners.delete(listener);
}

// ---- running one of our jobs ------------------------------------------------

/**
 * Post a job and resolve with its result once the queue has run it.
 *
 * The route validates and enqueues, answering `{prompt_id}` at once; the work
 * itself lands on `executed` under our own `continuity` key — see
 * `creator/jobs.py`. Which is why this is a helper rather than three copies:
 * the waiting is the same wait whatever was pressed.
 *
 * `client_id` goes in the body because `executed` is addressed to the tab that
 * queued the job, exactly as it is for a render.
 *
 * A refine on the remote backend answers with `{result}` in the reply itself —
 * no GPU here, nothing to queue behind — and this hands that straight back.
 * So does a plate with nothing cut out.
 *
 * `onQueued(promptId)` fires once the reply names the queue entry, for a
 * caller that may want to take it off the queue again — a picker closed while
 * its sheet was still waiting behind a render.
 */
export async function run(route, body, { onProgress, onQueued } = {}) {
  // Listening before asking. The server puts the job on the queue before it
  // answers, so a job short enough to finish inside the round trip had said
  // `executed` to a listener that did not exist yet, and the promise never
  // settled (issue #47). The collector is armed first, with the prompt id
  // filled in once the reply names it; what arrived in between is replayed.
  const pending = collect(onProgress);
  try {
    const response = await api.fetchApi(route, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...body, client_id: api.clientId }),
    });
    const answer = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(answer.error || t("that job could not be started ({status})",
                                        { status: response.status }));
    }
    if (answer.result !== undefined) { pending.abandon(); return answer.result; }
    if (!answer.prompt_id) throw new Error(t("the server queued nothing"));
    pending.expect(answer.prompt_id);
    onQueued?.(answer.prompt_id);
  } catch (error) {
    pending.abandon();
    throw error;
  }
  return await pending.promise;
}

/**
 * Wait for one queued job to finish. -> whatever its node put on the wire.
 *
 * Three ways out, because a queue has three: the job ran and said what it made;
 * the job raised, and the message is the one the person pressing needs to read;
 * or somebody pressed Cancel, which is now something that can happen to these
 * and did not used to be.
 *
 * Every listener comes off through `done`, whichever of the three fires. This
 * resolves once and is called once per press, so one left on would be a handler
 * per press for the life of the tab.
 */
function collect(onProgress) {
  let resolve, reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  const off = [];
  const done = (finish) => (...args) => {
    for (const remove of off) remove();
    finish(...args);
  };
  const settle = done(resolve);
  const fail = done(reject);

  // Until the reply names the prompt, every event is somebody's and is kept;
  // `expect` replays the kept ones against the id and drops the rest. Each
  // handler is wrapped the same way, so the ordering rule lives in one place.
  let promptId = null;
  const held = [];
  const on = (name, handler) => {
    const gated = (event) => {
      if (promptId === null) { held.push([name, event]); return; }
      if (event.detail?.prompt_id !== promptId) return;
      handler(event);
    };
    api.addEventListener(name, gated);
    off.push(() => api.removeEventListener(name, gated));
    return gated;
  };
  const handlers = {};
  const expect = (id) => {
    promptId = id;
    for (const [name, event] of held.splice(0)) handlers[name]?.(event);
  };
  const abandon = () => { for (const remove of off) remove(); };

    // The bar this job's node ticks — `jobs.progress()` on the server — arrives
    // on ComfyUI's own channel now, where it used to come back on a channel per
    // bench under a token they invented. The prompt holds one node, so the
    // busiest entry in it is ours; taking the max rather than the sole entry
    // keeps this honest if a job ever expands into more than one.
    if (onProgress) {
      handlers.progress_state = on("progress_state", ({ detail }) => {
        let best = null;
        for (const entry of Object.values(detail.nodes ?? {})) {
          if (!best || (entry.max ?? 0) > (best.max ?? 0)) best = entry;
        }
        // The fraction first, since that is what a bar wants; the raw pair
        // after it, because a refine counts tokens and "412/1024" says more
        // than "40%" about a thing that may stop early.
        if (best?.max) {
          onProgress(Math.max(0, Math.min(1, (best.value ?? 0) / best.max)),
                     best.value ?? 0, best.max);
        }
      });
    }

    handlers.executed = on("executed", ({ detail }) => {
      const result = detail.output?.continuity?.[0];
      // An `executed` for our prompt with nothing of ours in it is a node that
      // ran and returned a shape this does not know — a version skew worth
      // saying out loud rather than resolving with undefined.
      if (result === undefined) fail(new Error(t("the job finished without an answer")));
      else settle(result);
    });

    handlers.execution_error = on("execution_error", ({ detail }) => {
      fail(new Error(detail.exception_message || t("the job failed")));
    });

    handlers.execution_interrupted = on("execution_interrupted", ({ detail }) => {
      const cancelled = new Error(t("cancelled"));
      cancelled.cancelled = true;
      fail(cancelled);
    });

  return { promise, expect, abandon };
}

// ---- following a whole graph ------------------------------------------------

/**
 * Follow a prompt of many nodes — the image-to-3D build — rather than one job.
 *
 * `run` above waits for one `executed` and resolves with it, which is the whole
 * of a `ContinuityJob`. A graph of core's nodes says much more on the wire, and
 * all of it is worth hearing: every node's state and step count on
 * `progress_state`, each reporting node's output on `executed`, and one of
 * success, error or interruption at the end. So this hands every one of those
 * to the caller as it arrives, and resolves when the prompt is over.
 *
 * The same ordering rule as `collect`: armed before the POST goes out, with
 * whatever arrives before the reply names the prompt held and replayed against
 * it. A graph whose every node is cached can finish inside the round trip.
 *
 * `handlers` is `{progress(nodes), executed(node, output)}`; the promise
 * resolves on success, and rejects with the node's own message on an error or
 * with `cancelled` set on an interruption.
 *
 * -> `{expect(promptId), abandon(), promise}`.
 */
export function follow(handlers = {}) {
  let resolve, reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  const off = [];
  let promptId = null;
  const held = [];
  const stop = () => { for (const remove of off.splice(0)) remove(); };
  const table = {
    progress_state: ({ detail }) => handlers.progress?.(detail.nodes ?? {}),
    executed: ({ detail }) => handlers.executed?.(String(detail.node ?? detail.display_node ?? ""),
                                                 detail.output ?? {}),
    execution_success: () => { stop(); resolve(); },
    execution_error: ({ detail }) => {
      stop();
      const error = new Error(detail.exception_message || t("the job failed"));
      error.node = detail.node_id ?? null;
      reject(error);
    },
    execution_interrupted: () => {
      stop();
      const cancelled = new Error(t("cancelled"));
      cancelled.cancelled = true;
      reject(cancelled);
    },
  };
  for (const [name, handler] of Object.entries(table)) {
    const gated = (event) => {
      if (promptId === null) { held.push([name, event]); return; }
      if (event.detail?.prompt_id !== promptId) return;
      handler(event);
    };
    api.addEventListener(name, gated);
    off.push(() => api.removeEventListener(name, gated));
  }
  return {
    promise,
    expect(id) {
      promptId = id;
      for (const [name, event] of held.splice(0)) {
        if (event.detail?.prompt_id === promptId) table[name](event);
      }
    },
    abandon() { stop(); held.length = 0; },
  };
}

/** Stop one prompt: off the queue if it is still waiting, interrupted if it is
 *  the one running. Targeted by id, so a render that happens to be on the
 *  sampler instead is left alone. */
export async function stopPrompt(promptId) {
  await dropQueued(promptId);
  await api.fetchApi("/interrupt", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt_id: String(promptId) }),
  }).catch(() => {});
}
