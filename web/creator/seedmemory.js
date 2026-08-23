// What the last queued render actually ran on.
//
// The seed on the node is not the seed a finished render came from: the moment
// a queue goes out, `control_after_generate` may roll it on, and the number that
// made the shot you are looking at is gone from the UI. This remembers it, and
// the sampler row grows a button that puts it back — the only way back to a shot
// worth keeping once the seed has moved.
//
// Read off the *serialized* prompt rather than off the widget, because that is
// the one place the answer is not a guess: with `Comfy.WidgetControlMode` on
// "before" the control rolls the widget inside the queue call, and a value read
// on the way in would be the previous render's. What `graphToPrompt` returned is
// what the server was asked to run, in either mode.
//
// Keyed by the widget object: node ids renumber on paste and the widget survives
// it, and a WeakMap means a deleted node's seed is forgotten without anything
// having to remember to say so.

import { app } from "../../../scripts/app.js";

const LAST = new WeakMap();

/** The seed the last queue actually sent for this widget, or `null`. */
export function lastSeed(widget) {
  const seed = widget && LAST.get(widget);
  return typeof seed === "number" ? seed : null;
}

// Only a queue counts. `graphToPrompt` is also how a workflow is saved and
// exported, and neither of those ran anything.
let queuing = false;

/** Store what each of our nodes was serialized with, and redraw its row. */
function record(prompt) {
  for (const node of app.graph?._nodes || []) {
    if (!node.mmcBody) continue;
    const widget = node.widgets?.find((w) => w.name === "seed");
    if (!widget) continue;
    const seed = Number(prompt?.output?.[String(node.id)]?.inputs?.seed);
    if (!Number.isFinite(seed) || LAST.get(widget) === seed) continue;
    LAST.set(widget, seed);
    // The button is drawn off this, and a queue is not otherwise a reason for
    // the body to redraw.
    node.mmcBody.render?.();
  }
}

/** Install once, from the entry point. */
export function rememberQueuedSeeds() {
  const queue = app.queuePrompt;
  app.queuePrompt = async function (...args) {
    queuing = true;
    try {
      return await queue.apply(this, args);
    } finally {
      queuing = false;
    }
  };

  const serialize = app.graphToPrompt;
  app.graphToPrompt = async function (...args) {
    const prompt = await serialize.apply(this, args);
    if (queuing) record(prompt);
    return prompt;
  };
}
