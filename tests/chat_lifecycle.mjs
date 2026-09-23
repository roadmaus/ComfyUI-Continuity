// Run by layout.in_pack after the shared DOM shim. All production imports are
// loaded normally; drive the room through its buttons and observe its saves.
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
const response = body => ({ ok: true, json: async () => body });
const drain = async () => { for (let i = 0; i < 100; i++) await Promise.resolve(); };
const emit = lifecycle.emit;
const complete = id => emit("executed", {
  prompt_id: id, output: { mmc_image: [{ filename: `${id}.png`, type: "output" }] },
});
const one = (selector, root = document.body) => {
  const node = root.querySelector(selector);
  assert.ok(node, `Missing control: ${selector}`);
  return node;
};
async function click(node) {
  assert.ok(node, "The control exists");
  for (const handler of node.listeners.click ?? []) {
    await handler({ currentTarget: node, target: node, stopPropagation() {}, preventDefault() {} });
  }
  await drain();
}
async function save() {
  // Run the room's debounce after the action has settled. Rendering and writes
  // still take their normal promises; only the 600 ms wall-clock delay is skipped.
  for (const [id, timer] of [...timers]) {
    if (timer.after !== 600) continue;
    timers.delete(id);
    timer.run();
  }
  await drain();
}
const body = id => JSON.parse(files.get(`continuity.chat.${id}.json`));
const row = id => one(`.mmc-ch-siderow[data-id="${id}"]`);
async function enter(id) {
  await click(one(".mmc-ch-new"));
  await click(one(".mmc-ch-sideopenbtn", row(id)));
}
async function send(text) {
  one(".mmc-ch-box").replaceChildren(document.createTextNode(text));
  await click(one(".mmc-ch-send"));
}
async function remove(id) {
  await click(one('[title="Delete"]', row(id)));
  await click(one(".mmc-ch-sidedel"));
}
const render = (id, turn = 1) => ({ state: "left", turn, promptId: id,
  action: { act: "render", kind: "still", prompt: "A cat" } });
const fixture = card => ({ turn: 1, messages: [
  { role: "user", text: "A cat", turn: 1 },
  ...(card ? [{ role: "assistant", say: "Drawing", card }] : []),
], ledger: [], counts: { pic: 0, clip: 0, snd: 0 } });
const history = { turn: 2, messages: [], ledger: [], counts: { pic: 2 } };
for (let turn = 1; turn <= 2; turn++) {
  const entry = { handle: `pic-${turn}`, kind: "still", turn, filename: `pic-${turn}.png`, text: "A cat" };
  history.messages.push({ role: "user", text: `draw ${turn}`, turn },
    { role: "assistant", say: "Done", card: { state: "done", turn, entry } });
  history.ledger.push(entry);
}
for (const [id, state] of Object.entries({ history, saving: fixture(),
  ...Object.fromEntries(["active", "race", "pending", "refused", "deleted"].map(id =>
    [id, fixture(render(`${id}-prompt`))])),
})) await store.saveChat({ id, title: id, created: 1 }, state);
const closed = openChat();
await drain();

const results = {};
async function test(name, run) {
  try { await run(); results[name] = null; }
  catch (error) { results[name] = error.stack ?? error.message; }
  finally { lifecycle.beforeWrite = async () => {}; }
}

await test("reopen, send and edit preserves earlier references", async () => {
  lifecycle.http = async route => route === "/continuity/chat/turn" ? response({ result: { say: "Done" } }) : undefined;
  await enter("history");
  await send("draw a third picture");
  await save();
  const saved = body("history");
  assert.equal(saved.turn, 3);
  assert.equal(saved.messages[1].card.turn, 1);
  assert.equal(saved.messages[4].turn, 3);
  await click(document.body.querySelectorAll('[title="Edit and send again"]')[2]);
  await send("draw it differently");
  await save();
  assert.equal(body("history").messages[4].turn, 3);
  assert.deepEqual(body("history").ledger.map(entry => entry.handle), ["pic-1", "pic-2"]);
});

await test("legacy turns use saved, ledger and message maxima without inference", async () => {
  const messages = [
    { role: "user", text: "one", turn: 1 },
    { role: "assistant", card: { state: "done", entry: { turn: 1 } } },
    { role: "assistant", card: { state: "done", entry: { turn: 2 } } },
    { role: "user", text: "three", turn: 3 },
    { role: "assistant", card: { state: "left", promptId: "third" } },
  ];
  const restored = store.unpack({ messages, ledger: [{ turn: 1 }, { turn: 2 }] });
  assert.equal(restored.turn, 3);
  assert.equal(store.unpack({ turn: 6, messages, ledger: [{ turn: 4 }] }).turn, 6);
  assert.equal(store.unpack({ turn: 0, messages, ledger: [{ turn: 5 }] }).turn, 5);
  assert.equal(store.unpack({}).turn, 0);
  assert.ok(restored.messages.filter(message => message.card).every(message => message.card.turn === undefined));
  assert.deepEqual(restored.messages.filter(message => message.role === "user").map(message => message.turn), [1, 3]);
  assert.equal(store.pack({ ...restored, turn: 1 }).turn, 3, "an old in-flight home's turn cannot lower the save");
});

await test("restored active cancellation waits for the matching interruption", async () => {
  lifecycle.calls.length = 0;
  lifecycle.http = async (route, options) => {
    if (route.startsWith("/history/")) return response({});
    if (route === "/queue") return response({ queue_running: [[1, "active-prompt"]], queue_pending: [] });
    if (route === "/interrupt") return response({});
  };
  await enter("active");
  assert.equal(one(".mmc-ch-note").textContent, "Rendering…");
  await click(one(".mmc-ch-cancel"));
  assert.equal(one(".mmc-ch-note").textContent, "Rendering…", "HTTP acceptance is not confirmation");
  emit("execution_interrupted", { prompt_id: "someone-else" });
  assert.equal(one(".mmc-ch-note").textContent, "Rendering…");
  emit("execution_interrupted", { prompt_id: "active-prompt" });
  assert.equal(one(".mmc-ch-note").textContent, "cancelled");
  assert.deepEqual(lifecycle.calls.filter(call => call.route === "/interrupt").map(call =>
    JSON.parse(call.options.body)), [{ prompt_id: "active-prompt" }]);
});

await test("a pending prompt that starts during cancellation is targeted", async () => {
  let running = false;
  lifecycle.calls.length = 0;
  lifecycle.http = async (route, options) => {
    if (route.startsWith("/history/")) return response({});
    if (route === "/queue" && options?.method === "POST") { running = true; return response({}); }
    if (route === "/queue") return response({
      queue_running: running ? [[1, "race-prompt"]] : [], queue_pending: running ? [] : [[1, "race-prompt"]],
    });
    if (route === "/interrupt") return response({});
  };
  await enter("race");
  await click(one(".mmc-ch-cancel"));
  assert.equal(one(".mmc-ch-note").textContent, "Rendering…");
  assert.deepEqual(lifecycle.calls.filter(call => call.route === "/interrupt").map(call =>
    JSON.parse(call.options.body)), [{ prompt_id: "race-prompt" }]);
  complete("race-prompt"); // Completion may win the interrupt race.
  await save();
  assert.equal(body("race").messages[1].card.state, "done");
  assert.equal(body("race").ledger.length, 1);
});

await test("pending removal is confirmed and never interrupts another job", async () => {
  let pending = true;
  lifecycle.calls.length = 0;
  lifecycle.http = async (route, options) => {
    if (route.startsWith("/history/")) return response({});
    if (route === "/queue" && options?.method === "POST") {
      pending = false;
      return response({});
    }
    if (route === "/queue") return response({ queue_running: [[1, "other"]],
      queue_pending: pending ? [[2, "pending-prompt"]] : [] });
  };
  await enter("pending");
  await click(one(".mmc-ch-cancel"));
  assert.equal(one(".mmc-ch-note").textContent, "cancelled");
  assert.deepEqual(lifecycle.calls.filter(call => call.route === "/queue" && call.options?.method === "POST")
    .map(call => JSON.parse(call.options.body)), [{ delete: ["pending-prompt"] }]);
  assert.equal(lifecycle.calls.some(call => call.route === "/interrupt"), false);
});

await test("failed cancellation keeps the completion listener", async () => {
  lifecycle.http = async (route, options) => {
    if (route.startsWith("/history/")) return response({});
    if (route === "/queue") return options?.method === "POST"
      ? { ok: false, status: 500 } : response({ queue_pending: [[1, "refused-prompt"]], queue_running: [] });
  };
  await enter("refused");
  await click(one(".mmc-ch-cancel"));
  assert.equal(one(".mmc-ch-note").textContent, "Queued");
  assert.ok(document.body.text.includes("Could not cancel the render."));
  complete("refused-prompt");
  await save();
  assert.equal(body("refused").messages[1].card.state, "done");
  assert.equal(body("refused").ledger.length, 1);
});

await test("deleting a chat stays deleted after its render completes", async () => {
  lifecycle.http = async route => route === "/queue"
    ? response({ queue_running: [[1, "deleted-prompt"]], queue_pending: [] })
    : route.startsWith("/history/") ? response({}) : undefined;
  await enter("deleted");
  await save();
  await remove("deleted");
  complete("deleted-prompt");
  await save();
  assert.equal(files.has("continuity.chat.deleted.json"), false);
  assert.equal(localStorage.getItem("continuity-chat-deleted"), null);
  assert.equal((await store.listChats()).some(entry => entry.id === "deleted"), false);
});

await test("a first render shares the id assigned before autosave and deletion", async () => {
  lifecycle.http = async route => route === "/continuity/chat/turn"
    ? response({ result: { say: "Drawing", action: render("first-prompt").action } })
    : route === "/continuity/chat/render" ? response({ result: { prompt_id: "first-prompt" } }) : undefined;
  await click(one(".mmc-ch-new"));
  await send("first render");
  assert.equal(one(".mmc-ch-note").textContent, "Queued");
  await save();
  const id = (await store.listChats()).find(entry => entry.title === "first render").id;
  await remove(id);
  const before = [...files.keys()].sort();
  complete("first-prompt");
  await save();
  assert.deepEqual([...files.keys()].sort(), before, "completion must not create a different chat id");
  assert.equal(files.has(`continuity.chat.${id}.json`), false);
  assert.equal(localStorage.getItem(`continuity-chat-${id}`), null);
});

await test("deletion drains a save already writing before removing both copies", async () => {
  lifecycle.http = async route => route === "/continuity/chat/turn" ? response({ result: { say: "Done" } }) : undefined;
  await enter("saving");
  await send("one more message");
  let release, entered;
  const started = new Promise(resolve => { entered = resolve; });
  const held = new Promise(resolve => { release = resolve; });
  lifecycle.beforeWrite = async file => {
    if (file === "continuity.chat.saving.json") { entered(); await held; }
  };
  const saving = save();
  await Promise.race([started, drain().then(() => { throw new Error("The autosave did not start"); })]);
  const deletion = remove("saving");
  await drain();
  release();
  await Promise.all([saving, deletion]);
  assert.equal(files.has("continuity.chat.saving.json"), false);
  assert.equal(localStorage.getItem("continuity-chat-saving"), null);
  assert.equal((await store.listChats()).some(entry => entry.id === "saving"), false);
  assert.equal(document.body.querySelector('.mmc-ch-siderow[data-id="saving"]'), null);
  await store.saveChat({ id: "new-chat", title: "New" }, { messages: [{ role: "user", text: "new" }] });
  assert.equal(files.has("continuity.chat.new-chat.json"), true, "deletion must not suppress a new chat");
});

await click(one('[title="Close the room"]'));
await closed;
console.log(JSON.stringify(results));
