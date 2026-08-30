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

import { api } from "../../../scripts/api.js";
import { t } from "./i18n.js";

const listeners = new Set();

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
 */
export async function run(route, body, { onProgress } = {}) {
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
  if (answer.result !== undefined) return answer.result;
  if (!answer.prompt_id) throw new Error(t("the server queued nothing"));
  return await collect(answer.prompt_id, onProgress);
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
function collect(promptId, onProgress) {
  return new Promise((resolve, reject) => {
    const off = [];
    const done = (finish) => (...args) => {
      for (const remove of off) remove();
      finish(...args);
    };
    const settle = done(resolve);
    const fail = done(reject);

    const on = (name, handler) => {
      api.addEventListener(name, handler);
      off.push(() => api.removeEventListener(name, handler));
    };

    // The bar this job's node ticks — `jobs.progress()` on the server — arrives
    // on ComfyUI's own channel now, where it used to come back on a channel per
    // bench under a token they invented. The prompt holds one node, so the
    // busiest entry in it is ours; taking the max rather than the sole entry
    // keeps this honest if a job ever expands into more than one.
    if (onProgress) {
      on("progress_state", ({ detail }) => {
        if (detail?.prompt_id !== promptId) return;
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

    on("executed", ({ detail }) => {
      if (detail?.prompt_id !== promptId) return;
      const result = detail.output?.continuity?.[0];
      // An `executed` for our prompt with nothing of ours in it is a node that
      // ran and returned a shape this does not know — a version skew worth
      // saying out loud rather than resolving with undefined.
      if (result === undefined) fail(new Error(t("the job finished without an answer")));
      else settle(result);
    });

    on("execution_error", ({ detail }) => {
      if (detail?.prompt_id !== promptId) return;
      fail(new Error(detail.exception_message || t("the job failed")));
    });

    on("execution_interrupted", ({ detail }) => {
      if (detail?.prompt_id !== promptId) return;
      const cancelled = new Error(t("cancelled"));
      cancelled.cancelled = true;
      fail(cancelled);
    });
  });
}
