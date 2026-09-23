// Exercise the complete room/store/queue modules with no browser, server or GPU.
// Only the room's private state is exposed; its methods and imports stay intact.
import fs from "node:fs";
import vm from "node:vm";
import path from "node:path";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";

const root = process.argv[2] ?? path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const files = new Map(), mirror = new Map(), listeners = new Map(), calls = [];
let http = async () => ({ ok: true, json: async () => ({}) });
let beforeWrite = async () => {};
const api = {
  clientId: "test-client",
  addEventListener(name, listener) {
    if (!listeners.has(name)) listeners.set(name, new Set());
    listeners.get(name).add(listener);
  },
  removeEventListener(name, listener) { listeners.get(name)?.delete(listener); },
  dispatchEvent(event) { for (const fn of [...(listeners.get(event.type) ?? [])]) fn(event); },
  async fetchApi(route, options) { calls.push({ route, options }); return http(route, options); },
  async getUserData(file) {
    return files.has(file) ? { status: 200, json: async () => JSON.parse(files.get(file)) } : { status: 404 };
  },
  async storeUserData(file, body) {
    await beforeWrite(file, body);
    files.set(file, JSON.stringify(body));
    return { status: 200 };
  },
  async deleteUserData(file) { files.delete(file); return { status: 204 }; },
  interrupt() { throw new Error("Cancellation must never issue a global interrupt"); },
};
const context = vm.createContext({ console, URL, Blob, Date, Math,
  setTimeout: () => 1, clearTimeout() {},
  localStorage: {
    getItem: key => mirror.get(key) ?? null,
    setItem: (key, value) => mirror.set(key, value), removeItem: key => mirror.delete(key),
  },
  CustomEvent: class { constructor(type, init) { this.type = type; Object.assign(this, init); } },
});
const dependencies = {
  api, app: {}, t: text => text,
  el: (tag, props, children = []) => ({ tag, props, children }),
  DEFAULT_VIDEO_FAMILY: "h3", DEFAULT_STILL_ARCH: "krea2", PRESTAGE_DEFAULT_EDGE: 1024,
  PICTURE_ARCHES: ["krea2"], STILL_ARCHES: { krea2: "krea2" },
  uiSetting: (_key, fallback) => fallback, patchSettings() {},
  rulesFor: () => ({ nativeShortEdge: 720 }), pinsFor: () => [],
  emptyPreStage: () => ({ arch: "krea2" }), serializePreStage: JSON.stringify,
};
const sources = Object.fromEntries(["chat.js", "chatstore.js", "queue.js"].map(name =>
  [name, fs.readFileSync(path.join(root, "web/creator", name), "utf8")]));
const imports = new Map();
for (const source of Object.values(sources)) {
  for (const [, clause, specifier] of source.matchAll(/^import\s+([\s\S]*?)\s+from\s+["']([^"']+)["'];/gm)) {
    if (!imports.has(specifier)) imports.set(specifier, new Set());
    const names = imports.get(specifier);
    if (clause.trim().startsWith("*")) {
      for (const name of ["emptyPreStage", "serializePreStage"]) names.add(name);
    } else {
      for (const item of clause.replace(/[{}]/g, "").split(",")) names.add(item.trim().split(/\s+as\s+/)[0]);
    }
  }
}
const modules = new Map();
for (const [name, source] of Object.entries(sources)) {
  const expose = name === "chat.js"
    ? "\nexport const testRoom = {state, home, saveNow, reset, openSaved, settle, watchRender, room: Object.create(Room.prototype)};\n" : "";
  modules.set(`./${name}`, new vm.SourceTextModule(source + expose, { context, identifier: path.join(root, name) }));
}
for (const [specifier, names] of imports) {
  if (!modules.has(specifier)) modules.set(specifier, new vm.SyntheticModule([...names], function () {
    for (const name of names) this.setExport(name, dependencies[name]);
  }, { context, identifier: `mock:${specifier}` }));
}
const chat = modules.get("./chat.js");
await chat.link(specifier => modules.get(specifier));
await chat.evaluate();
const roomState = chat.namespace.testRoom;
const { state, room } = roomState;
const store = modules.get("./chatstore.js").namespace;
room.paint = room.paintSide = () => {};
room.ask = async () => {};
room.pending = [];
room.sync = { videoFamily: () => "h3", stillArch: () => "krea2",
  row: () => ({ loras: [], sampling: {}, widgets: {}, turbo: null }) };
const plain = value => JSON.parse(JSON.stringify(value));
const emit = (type, detail) => api.dispatchEvent({ type, detail });
const drain = async () => { for (let i = 0; i < 40; i++) await Promise.resolve(); };
const complete = id => emit("executed", {
  prompt_id: id, output: { mmc_image: [{ filename: `${id}.png`, type: "output" }] },
});
const failures = [];
let passed = 0;
async function test(name, run) {
  try { await run(); passed++; }
  catch (error) { failures.push(`${name}: ${error.message}`); }
}
function newHome(id) {
  roomState.reset();
  state.chat = { id, title: id, created: 1 };
  state.turn = 1;
  state.messages.push({ role: "user", text: "A cat", turn: 1 });
}
function renderCard(id) {
  const card = { state: "left", turn: 1, promptId: id,
    action: { act: "render", kind: "still", prompt: "A cat" } };
  state.messages.push({ role: "assistant", say: "Drawing", card });
  return card;
}
const response = body => ({ ok: true, json: async () => body });

await test("reopen, send and edit preserves earlier references", async () => {
  newHome("history");
  state.messages = [];
  state.turn = 2;
  for (let turn = 1; turn <= 2; turn++) {
    const entry = { handle: `pic-${turn}`, kind: "still", turn, filename: `pic-${turn}.png`, text: "A cat" };
    state.messages.push({ role: "user", text: `draw ${turn}`, turn },
      { role: "assistant", say: "Done", card: { state: "done", turn, entry } });
    state.ledger.push(entry);
  }
  state.counts.pic = 2;
  await roomState.saveNow();
  const saved = JSON.parse(files.get("continuity.chat.history.json"));
  roomState.reset();
  await roomState.openSaved("history");
  room.box = { getValue: () => "draw a third picture", setValue() {}, root: { focus() {} } };
  await room.send();
  const next = state.messages.at(-1).turn;
  room.edit(4);
  assert.equal(saved.turn, 2);
  assert.equal(saved.messages[1].card.turn, 1);
  assert.equal(next, 3);
  assert.deepEqual(plain(state.ledger.map(entry => entry.handle)), ["pic-1", "pic-2"]);
});

await test("legacy turns and card-only retakes are inferred", async () => {
  const restored = store.unpack({ turn: 0, messages: [
    { role: "user", text: "one", turn: 1 },
    { role: "assistant", card: { state: "done", entry: { turn: 1 } } },
    { role: "assistant", card: { state: "done", entry: { turn: 2 } } },
    { role: "user", text: "three", turn: 3 },
    { role: "assistant", card: { state: "left", promptId: "third" } },
  ], ledger: [{ turn: 1 }, { turn: 2 }] });
  assert.equal(restored.turn, 3);
  assert.deepEqual(plain(restored.messages.filter(message => message.card).map(message => message.card.turn)), [1, 2, 3]);
  assert.equal(store.pack({ ...restored, turn: 1 }).turn, 3, "an old in-flight home's turn cannot lower the save");
});

await test("restored active cancellation waits for the matching interruption", async () => {
  newHome("active");
  const card = renderCard("active-prompt");
  calls.length = 0;
  http = async (route, options) => {
    if (route.startsWith("/history/")) return response({});
    if (route === "/queue") return response({ queue_running: [[1, card.promptId]], queue_pending: [] });
    if (route === "/interrupt") {
      assert.equal(JSON.parse(options.body).prompt_id, card.promptId);
      return response({});
    }
    throw new Error(`Unexpected ${route}`);
  };
  await roomState.settle(card, roomState.home());
  assert.equal(card.state, "running");
  await room.cancel(card);
  assert.equal(card.state, "running", "HTTP acceptance is not interruption confirmation");
  emit("execution_interrupted", { prompt_id: "someone-else" });
  assert.equal(card.state, "running");
  emit("execution_interrupted", { prompt_id: card.promptId });
  assert.equal(card.state, "failed");
  assert.equal(card.error, "cancelled");
  assert.equal(calls.filter(call => call.route === "/interrupt").length, 1);
});

await test("a pending prompt that starts during cancellation is targeted", async () => {
  newHome("race");
  const card = renderCard("race-prompt");
  card.state = "queued";
  card.home = roomState.home();
  roomState.watchRender(card);
  let running = false;
  http = async (route, options) => {
    if (route === "/queue" && options?.method === "POST") { running = true; return response({}); }
    if (route === "/queue") return response({
      queue_running: running ? [[1, card.promptId]] : [], queue_pending: running ? [] : [[1, card.promptId]],
    });
    if (route === "/interrupt") {
      assert.equal(JSON.parse(options.body).prompt_id, card.promptId);
      return response({});
    }
    throw new Error(`Unexpected ${route}`);
  };
  await room.cancel(card);
  assert.equal(card.state, "running");
  complete(card.promptId); // Completion can win the interrupt race and must still land.
  assert.equal(card.state, "done");
  assert.equal(state.ledger.length, 1);
});

await test("pending removal is confirmed and never interrupts another job", async () => {
  newHome("pending");
  const card = renderCard("pending-prompt");
  card.state = "queued";
  card.home = roomState.home();
  roomState.watchRender(card);
  let pending = true;
  calls.length = 0;
  http = async (route, options) => {
    if (route.startsWith("/history/")) return response({});
    if (route === "/queue" && options?.method === "POST") { pending = false; return response({}); }
    if (route === "/queue") return response({ queue_running: [[1, "other"]],
      queue_pending: pending ? [[2, card.promptId]] : [] });
    throw new Error(`Unexpected ${route}`);
  };
  await room.cancel(card);
  assert.equal(card.state, "failed");
  assert.equal(calls.some(call => call.route === "/interrupt"), false);
});

await test("failed cancellation keeps the completion listener", async () => {
  newHome("refused");
  const card = renderCard("refused-prompt");
  card.state = "queued";
  card.home = roomState.home();
  roomState.watchRender(card);
  http = async (route, options) => options?.method === "POST"
    ? { ok: false, status: 500 } : response({ queue_pending: [[1, card.promptId]], queue_running: [] });
  await room.cancel(card);
  assert.equal(card.state, "queued");
  complete(card.promptId);
  assert.equal(card.state, "done");
  assert.equal(state.ledger.length, 1);
});

await test("deleting a chat stays deleted after its render completes", async () => {
  newHome("deleted");
  const card = renderCard("delete-prompt");
  card.state = "running";
  card.home = roomState.home();
  roomState.watchRender(card);
  await roomState.saveNow();
  const confirm = room.confirmRow({ id: "deleted" });
  await confirm.children[1].children[0].props.onclick();
  complete(card.promptId);
  await drain();
  assert.equal(files.has("continuity.chat.deleted.json"), false);
  assert.equal(mirror.has("continuity-chat-deleted"), false);
  assert.equal((await store.listChats()).some(entry => entry.id === "deleted"), false);
});

await test("a first render shares the id assigned before autosave and deletion", async () => {
  roomState.reset();
  state.turn = 1;
  state.messages.push({ role: "user", text: "first render", turn: 1 });
  const card = renderCard("first-prompt");
  card.state = "running";
  card.home = roomState.home();
  roomState.watchRender(card);
  await roomState.saveNow();
  const id = state.chat.id;
  const sharedId = card.home.chat?.id;
  const confirm = room.confirmRow({ id });
  await confirm.children[1].children[0].props.onclick();
  const before = [...files.keys()].sort();
  complete(card.promptId);
  await drain();
  assert.equal(sharedId, id);
  assert.deepEqual([...files.keys()].sort(), before, "completion must not create a different chat id");
  assert.equal(files.has(`continuity.chat.${id}.json`), false);
});

await test("deletion drains a save already writing before removing both copies", async () => {
  newHome("saving");
  let release, entered;
  const started = new Promise(resolve => { entered = resolve; });
  const held = new Promise(resolve => { release = resolve; });
  beforeWrite = async file => {
    if (file === "continuity.chat.saving.json") { entered(); await held; }
  };
  const save = roomState.saveNow();
  await started;
  const deletion = store.deleteChat("saving");
  await drain();
  release();
  await Promise.all([save, deletion]);
  beforeWrite = async () => {};
  assert.equal(files.has("continuity.chat.saving.json"), false);
  assert.equal(mirror.has("continuity-chat-saving"), false);
  assert.equal((await store.listChats()).some(entry => entry.id === "saving"), false);
  assert.equal(state.index.some(entry => entry.id === "saving"), false);
  await store.saveChat({ id: "new-chat", title: "New" }, { messages: [{ role: "user", text: "new" }] });
  assert.equal(files.has("continuity.chat.new-chat.json"), true, "deletion must not suppress a new chat");
});

if (failures.length) {
  for (const failure of failures) console.error(failure);
  process.exitCode = 1;
}
console.log(`${passed} chat lifecycle scenarios passed; ${failures.length} failed`);
