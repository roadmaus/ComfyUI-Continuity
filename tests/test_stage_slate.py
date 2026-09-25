"""A render that never started, or failed upstream, says so on the stage.

    python3 tests/test_stage_slate.py

Three ways a press ends without a picture, and where each used to go:

- The server refused the prompt (a missing file in a combo, a required input
  unwired). ComfyUI's frontend catches that itself and, since its errors tab
  arrived, reports it in a side-panel tab and as node badges — both behind the
  fullscreen shell. `queue.js` now hears the refusal on its way past and says
  it on the api as `mmc_refused`.
- The run raised in a node the press did not emit — a loader wired in upstream.
  The stage only claimed errors under its own id, so it sat idle.
- The run raised in the node's own expansion, which already reached the stage.

All three land on the slate. Driven here against a stub api whose
`queuePrompt` is made to refuse, with the stage's own listeners dispatched by
hand. Skips itself if node is not installed.
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
globalThis.__refuseWith = null;
export const api = {
  clientId: "test",
  addEventListener(type, fn) { (listeners[type] ??= []).push(fn); },
  removeEventListener(type, fn) {
    listeners[type] = (listeners[type] ?? []).filter((f) => f !== fn);
  },
  dispatchEvent(event) { globalThis.__say(event.type, event.detail); },
  apiURL: (u) => u,
  async queuePrompt(number, body, options) {
    if (globalThis.__refuseWith) {
      const error = new Error("refused");
      error.response = globalThis.__refuseWith;
      throw error;
    }
    return { prompt_id: options?.promptId ?? "p1" };
  },
  async fetchApi(url) {
    if (String(url).startsWith("/continuity/families")) {
      const body = readFileSync(new URL("./families.json", import.meta.url), "utf8");
      return { ok: true, status: 200, json: async () => JSON.parse(body) };
    }
    return { ok: true, status: 200, json: async () => ({}) };
  },
  async getUserData() { return { status: 404, json: async () => null }; },
  async storeUserData() { return { status: 200 }; },
};
"""

CHECK = """
await import("./dom.mjs");
const { api } = await import("../scripts/api.js");
const { Stage } = await import("./web/creator/stage.js");
const out = {};
const text = (stage) => stage.root.textContent.replace(/\\s+/g, " ").trim();
// The lightweight shim stores each element's own text rather than aggregating
// descendants; the labeled clocks now have separate label/value spans.
const chipText = (node) => node.textContent + node.children.map(chipText).join("");
const slate = (stage) => ({
  state: stage.state,
  showing: stage.showing(),
  lead: stage.root.querySelector(".mmc-stage-slate-lead")?.textContent ?? null,
  items: [...stage.root.querySelectorAll(".mmc-stage-slate-item")].map((item) => [
    item.querySelector(".mmc-stage-slate-where")?.textContent ?? null,
    item.querySelector(".mmc-stage-slate-what")?.textContent ?? null,
  ]),
  chips: [...stage.root.querySelectorAll(".mmc-stage-chip")].map(chipText),
});

const graph = {
  output: {
    "4": { class_type: "CheckpointLoaderSimple", _meta: { title: "Load Checkpoint" }, inputs: {} },
    "7": { class_type: "ContinuityCreator", _meta: { title: "Continuity" }, inputs: {} },
    "9": { class_type: "ContinuityCreator", _meta: { title: "Other piece" }, inputs: {} },
  },
};
const ours = new Stage({ nodeId: () => 7 });
const other = new Stage({ nodeId: () => 9 });
const stranger = new Stage({ nodeId: () => 12 });

// A refused press names its target; the stage the press was for shows the
// server's reasons, the other piece in the graph stays quiet.
globalThis.__refuseWith = {
  error: { type: "prompt_outputs_failed_validation", message: "Prompt outputs failed validation" },
  node_errors: {
    "4": { class_type: "CheckpointLoaderSimple", errors: [
      { type: "value_not_in_list", message: "Value not in list",
        details: "ckpt_name: 'missing.safetensors' not in ['a.safetensors']" },
    ] },
  },
};
await api.queuePrompt(0, graph, { partialExecutionTargets: ["7"] }).catch(() => {});
out.refusedOurs = slate(ours);
out.refusedOther = slate(other);
out.refusedStranger = slate(stranger);

// A refusal with no node to blame still lands on whoever was pressed.
ours.reset();
globalThis.__refuseWith = { error: { type: "prompt_no_outputs", message: "Prompt has no outputs" } };
await api.queuePrompt(0, graph, { partialExecutionTargets: ["7"] }).catch(() => {});
out.refusedTop = slate(ours);

// An accepted press, then a raise in the loader upstream: the stage that
// pressed claims it by the prompt, with the loader named as where.
ours.reset();
globalThis.__refuseWith = null;
await api.queuePrompt(0, graph, { partialExecutionTargets: ["7"], promptId: "p-up" });
globalThis.__say("execution_start", { prompt_id: "p-up" });
globalThis.__say("execution_error", {
  prompt_id: "p-up", node_id: "4", node_type: "CheckpointLoaderSimple",
  exception_message: "ERROR: Could not detect model type of: a.safetensors",
});
out.upstream = slate(ours);
out.upstreamOther = slate(other);

// A raise inside our own expansion names no where — the card is the where.
ours.reset();
globalThis.__say("execution_start", { prompt_id: "p-own" });
globalThis.__say("execution_error", {
  prompt_id: "p-own", node_id: "7.3", node_type: "MMCSampler",
  exception_message: "a plate needs at least one picture",
});
out.own = slate(ours);

// Somebody else's prompt failing, with our stage idle, is not our failure.
ours.reset();
globalThis.__say("execution_start", { prompt_id: "p-foreign" });
globalThis.__say("execution_error", {
  prompt_id: "p-foreign", node_id: "40", node_type: "KSampler", exception_message: "oom",
});
out.foreign = slate(ours);

// A second press refused while the first is on the sampler rides the readout
// rather than covering the live picture.
ours.reset();
globalThis.__say("execution_start", { prompt_id: "p-live" });
globalThis.__say("progress_state", { prompt_id: "p-live", nodes: {
  "7.3": { node_id: "7.3", parent_node_id: "7", state: "running", value: 3, max: 20 },
} });
globalThis.__refuseWith = { error: { type: "prompt_no_outputs", message: "Prompt has no outputs" } };
await api.queuePrompt(0, graph, { partialExecutionTargets: ["7"] }).catch(() => {});
globalThis.__refuseWith = null;
out.midRun = { ...slate(ours), text: text(ours) };

// The next run's first word clears the slate, as it clears a finished take.
ours.fail([{ where: null, what: "x" }], { started: false });
globalThis.__say("execution_start", { prompt_id: "p-next" });
globalThis.__say("progress_state", { prompt_id: "p-next", nodes: {
  "7.3": { node_id: "7.3", parent_node_id: "7", state: "running", value: 1, max: 20 },
} });
out.cleared = { state: ours.state, slate: ours.root.querySelector(".mmc-stage-slate") !== null };

// The ticker `begin` started would keep node alive past the report.
for (const stage of [ours, other, stranger]) stage.destroy();
console.log(JSON.stringify(out));
"""

with layout.pack(skip=["atlas"], extra_stubs={"api.js": API}) as target:
    got = layout.in_pack(CHECK.replace('await import("./dom.mjs");', DOM), target)

check("a refused press opens the slate on the stage it was for", got["refusedOurs"], {
    "state": "failed", "showing": True, "lead": "The render did not start.",
    "items": [["Load Checkpoint",
               "Value not in list: ckpt_name: 'missing.safetensors' not in ['a.safetensors']"]],
    "chips": [],
})
check("...and not on another piece in the same graph", got["refusedOther"]["state"], "idle")
check("...nor on a node the graph did not hold", got["refusedStranger"]["state"], "idle")
check("a refusal with no node to blame is still said",
      got["refusedTop"]["items"], [[None, "Prompt has no outputs"]])
check("a raise upstream is claimed by the press and names the node", got["upstream"], {
    "state": "failed", "showing": True, "lead": "The render failed.",
    "items": [["Load Checkpoint", "ERROR: Could not detect model type of: a.safetensors"]],
    "chips": [],
})
check("...and only by the press", got["upstreamOther"]["state"], "idle")
check("a raise in our own expansion names no where",
      got["own"]["items"], [[None, "a plate needs at least one picture"]])
check("somebody else's failure is not ours", got["foreign"]["state"], "idle")
check("a press refused mid-run rides the readout over the live picture",
      (got["midRun"]["state"], got["midRun"]["lead"], got["midRun"]["chips"]),
      ("sampling", None, ["3 / 20", "Next render not started: Prompt has no outputs",
                          "Total execution0:00", "Render window0:00"]))
check("the next run's first word clears the slate", got["cleared"], {"state": "sampling", "slate": False})

passed("a render that never started, or failed upstream, says so on the stage")
