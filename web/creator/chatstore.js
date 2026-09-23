// Saved conversations: where a chat goes when you leave it, and how it comes back.
//
// The room's state was the page's — leave and return, keep it; reload, lose
// it. That was the first iteration's line (§5.6) and it held until there was
// something worth coming back for: a conversation *is* its renders, and a
// still you made yesterday should be a press away, in the exchange that made
// it, not a file to hunt for in the gallery with its context gone.
//
// **The shape is the preset library's.** One small index file naming every
// conversation — id, title, dates, the last render as a cover — and one file
// per conversation holding the whole exchange. Opening the list reads one
// file; opening a chat reads one more; a keystroke in the composer writes
// nothing, and a turn writes the one chat it changed. Both go through
// ComfyUI's userdata API so they follow the user across browsers, with a
// localStorage mirror for a frontend that has no such API, the same deal the
// picker's favorites and the presets have.
//
// **What is kept is what draws the transcript.** `pack` takes the room's live
// state — messages with their render cards, the ledger, the handle counters —
// and keeps the fields the transcript and the next turn read, dropping what
// belongs to the moment: preview frames, progress, the listeners on a card.
// `unpack` gives it back in the shape `chat.js` holds it, so a restored chat
// is the same object a live one is and everything downstream is unchanged.
//
// Nothing here talks to the model or the queue. It is the shelf.

import { api } from "../../../scripts/api.js";
import { t } from "./i18n.js";

const INDEX_FILE = "continuity.chats.json";
const BODY_FILE = (id) => `continuity.chat.${id}.json`;
const INDEX_KEY = "continuity-chats";
const BODY_KEY = (id) => `continuity-chat-${id}`;
// A render may finish after its conversation was deleted. Keep that old home
// from writing again, and let any save already in flight finish before removal.
const deleted = new Set();
const writing = new Map();

/** How long a title may run. About what a sidebar row shows before the
 *  ellipsis, so the automatic title is never cut mid-word by the row. */
export const TITLE_LENGTH = 48;

// ---- files ------------------------------------------------------------------

async function readUserData(file, key) {
  try {
    const response = await api.getUserData(file);
    if (response.status === 200) return await response.json();
    // 404 is a shelf nobody has written to yet; anything else is the API
    // being away, and the mirror is the next place to look either way.
  } catch { /* no userdata API, or offline */ }
  try {
    return JSON.parse(localStorage.getItem(key) ?? "null");
  } catch { return null; }
}

async function writeUserData(file, key, value) {
  const body = JSON.stringify(value);
  try { localStorage.setItem(key, body); } catch { /* quota; userdata still tries */ }
  try {
    const response = await api.storeUserData(file, value, { stringify: true });
    if (response && response.status >= 400) {
      throw new Error(t("the server refused it ({status})", { status: response.status }));
    }
  } catch (error) {
    // Reported rather than swallowed: a chat that looked saved and was not is
    // a conversation the user believes they still have. The mirror above is
    // why this is a warning and not a loss.
    throw new Error(t("Could not save the chat — {error}", { error: error.message ?? error }));
  }
}

async function removeUserData(file, key) {
  try { localStorage.removeItem(key); } catch { /* denied */ }
  try { await api.deleteUserData?.(file); } catch { /* already gone, or no API */ }
}

// ---- the index --------------------------------------------------------------

/** Every saved conversation, newest first. -> `[{id, title, created, updated,
 *  renders, cover, coverKind}]`. An empty shelf is an empty list. */
export async function listChats() {
  const index = await readUserData(INDEX_FILE, INDEX_KEY);
  const entries = Array.isArray(index?.chats) ? index.chats : [];
  return entries
    .filter((entry) => entry && typeof entry.id === "string")
    .sort((a, b) => (b.updated ?? 0) - (a.updated ?? 0));
}

async function writeIndex(entries) {
  await writeUserData(INDEX_FILE, INDEX_KEY, { version: 1, chats: entries });
}

/** A new id: the time it was started, which is also what sorts it, plus a
 *  few random characters so two rooms started in the same millisecond on two
 *  tabs are two chats. */
export function newId(now = Date.now()) {
  return `${now.toString(36)}${Math.random().toString(36).slice(2, 6)}`;
}

/**
 * The automatic title: the first thing that was said, cut at a word.
 *
 * ChatGPT asks the model for one; here the model may be a 4B on the same GPU
 * as the render, and a title is not worth a queue slot. The first message is
 * what the user would type into a search for it anyway. Attachments arrive
 * with a note about their handles under the words, which is the server's to
 * read, not a name.
 */
export function titleFor(text, limit = TITLE_LENGTH) {
  const line = String(text ?? "").split("\n(attached:")[0].replace(/\s+/g, " ").trim();
  if (!line) return "";
  if (line.length <= limit) return line;
  const cut = line.slice(0, limit + 1);
  const space = cut.lastIndexOf(" ");
  return `${(space > limit * 0.6 ? cut.slice(0, space) : cut.slice(0, limit)).replace(/[,;:.\-–—]+$/, "")}…`;
}

// ---- one conversation -------------------------------------------------------

/** The fields a saved render card keeps: enough to draw a finished one, and
 *  enough to settle an unfinished one from the queue's history. */
function packCard(card) {
  if (!card) return null;
  return {
    action: card.action ?? null,
    state: card.state === "done" || card.state === "failed" ? card.state : "left",
    promptId: card.promptId ?? null,
    turn: card.turn ?? card.entry?.turn ?? null,
    saved: card.saved ?? null,
    isClip: Boolean(card.isClip),
    entry: card.entry ?? null,
    piece: card.piece ?? null,
    error: card.error ?? null,
    // The slate's numbers. Absent on a card saved before it had a back.
    seed: card.seed ?? null,
    took: card.took ?? null,
    landedAt: card.landedAt ?? null,
  };
}

function packMessage(message) {
  if (message.role === "user") {
    // The turn it was said on, so a reopened chat can be cut back to it —
    // the ledger's lines carry the same number.
    return { role: "user", text: message.text ?? "", attached: message.attached ?? [],
             ...(message.turn ? { turn: message.turn } : {}) };
  }
  return {
    role: "assistant",
    say: message.say ?? "",
    ...(message.bad ? { bad: true } : {}),
    ...(message.action ? { action: message.action } : {}),
    ...(message.card ? { card: packCard(message.card) } : {}),
  };
}

/**
 * The conversation as a file. -> `{version, messages, ledger, counts, turn}`.
 *
 * The room's own bubbles — the first run's three questions — are marked
 * `local` and left out: they were the room's, not the conversation's, and
 * what they decided is on the rail.
 */
export function pack(state) {
  return {
    version: 1,
    messages: (state.messages ?? []).filter((message) => !message.local).map(packMessage),
    ledger: state.ledger ?? [],
    strip: state.strip ?? [],
    counts: { pic: 0, clip: 0, snd: 0, ...(state.counts ?? {}) },
    turn: Math.max(state.turn ?? 0, ...(state.messages ?? []).map((message) =>
      message.turn ?? message.card?.turn ?? message.card?.entry?.turn ?? 0),
      ...(state.ledger ?? []).map((entry) => entry.turn ?? 0)),
    // The chat's own piece: who is cast and the files they are built from.
    // Nothing else of a piece is the conversation's — the family, the row and
    // the stack are assembled at render time from the rail and the pins.
    piece: packPiece(state.piece),
  };
}

/** The two things a chat's piece keeps. */
export function packPiece(piece) {
  return {
    subjects: Array.isArray(piece?.subjects) ? piece.subjects : [],
    assets: Array.isArray(piece?.assets) ? piece.assets : [],
  };
}

/** A file back into the room's shape. Cards come back without their
 *  listeners; `chat.js` settles any that were left mid-render. */
export function unpack(body) {
  const messages = (Array.isArray(body?.messages) ? body.messages : [])
    .map((message) => ({ ...message, card: message.card ? { ...message.card } : undefined }));
  const ledger = Array.isArray(body?.ledger) ? body.ledger : [];
  return {
    messages,
    ledger,
    strip: Array.isArray(body?.strip) ? body.strip : [],
    counts: { pic: 0, clip: 0, snd: 0, ...(body?.counts ?? {}) },
    // Older saves omitted the home's turn. User messages and ledger entries
    // already carry it, including retakes, so no transcript inference is needed.
    turn: Math.max(Number.isFinite(body?.turn) ? body.turn : 0,
      ...messages.map((message) => Number.isFinite(message.turn) ? message.turn : 0),
      ...ledger.map((entry) => Number.isFinite(entry.turn) ? entry.turn : 0)),
    piece: packPiece(body?.piece),
  };
}

/** The last thing this conversation made, for the row: its file and kind. */
export function coverOf(state) {
  for (let i = (state.messages ?? []).length - 1; i >= 0; i -= 1) {
    const entry = state.messages[i]?.card?.entry;
    if (entry?.filename && entry.kind !== "sound") {
      return { cover: entry.filename, coverKind: entry.kind };
    }
  }
  return { cover: null, coverKind: null };
}

function rendersIn(state) {
  return (state.messages ?? []).filter((message) => message.card?.entry).length;
}

/** The whole conversation, or null when there is no such chat. */
export async function loadChat(id) {
  const body = await readUserData(BODY_FILE(id), BODY_KEY(id));
  return body ? unpack(body) : null;
}

/**
 * Write one conversation and its line in the index.
 *
 * `meta` is `{id, title, created}`; the index line is rebuilt from the state
 * every time rather than patched, so the cover and the count can never drift
 * from the file. -> the index line written, or null if this home was deleted.
 */
export async function saveChat(meta, state, now = Date.now()) {
  if (deleted.has(meta.id)) return null;
  const pending = (writing.get(meta.id) ?? Promise.resolve()).catch(() => {}).then(async () => {
    if (deleted.has(meta.id)) return null;
    return writeChat(meta, state, now);
  });
  writing.set(meta.id, pending);
  try {
    const line = await pending;
    return deleted.has(meta.id) ? null : line;
  } finally {
    if (writing.get(meta.id) === pending) writing.delete(meta.id);
  }
}

async function writeChat(meta, state, now) {
  const line = {
    id: meta.id,
    title: meta.title || titleFor(state.messages?.find((m) => m.role === "user")?.text) || t("New chat"),
    created: meta.created ?? now,
    updated: now,
    renders: rendersIn(state),
    ...coverOf(state),
  };
  await writeUserData(BODY_FILE(meta.id), BODY_KEY(meta.id), pack(state));
  const entries = (await listChats()).filter((entry) => entry.id !== meta.id);
  await writeIndex([line, ...entries]);
  return line;
}

/** A new name for a chat. The body is untouched: the title lives in the index
 *  alone, so renaming a forty-render conversation writes a few hundred bytes. */
export async function renameChat(id, title) {
  const clean = String(title ?? "").replace(/\s+/g, " ").trim();
  if (!clean) return null;
  const entries = await listChats();
  const line = entries.find((entry) => entry.id === id);
  if (!line) return null;
  line.title = clean;
  await writeIndex(entries);
  return line;
}

/** Gone from the shelf and the index. The renders stay: they are files in the
 *  output folder, and deleting a conversation about them is not deleting them. */
export async function deleteChat(id) {
  deleted.add(id);
  await writing.get(id)?.catch(() => {});
  await removeUserData(BODY_FILE(id), BODY_KEY(id));
  const entries = (await listChats()).filter((entry) => entry.id !== id);
  await writeIndex(entries);
}

// ---- the list's shape -------------------------------------------------------

/** The sidebar's headings, in the order they are shown. Each is a function
 *  of the entry's age in days at the start of today, so "Yesterday" is the
 *  calendar's yesterday and not the last twenty-four hours. */
const GROUPS = [
  ["Today", (days) => days < 1],
  ["Yesterday", (days) => days < 2],
  ["Earlier this week", (days) => days < 7],
  ["Older", () => true],
];

/**
 * The entries under their day headings. -> `[[heading, [entries]]]`, headings
 * with nothing under them left out. `now` is a timestamp; the day boundary is
 * local midnight, which is what "today" means to the person looking.
 */
export function groupByDay(entries, now = Date.now()) {
  const today = new Date(now);
  today.setHours(0, 0, 0, 0);
  const start = today.getTime();
  const out = new Map();
  for (const entry of entries) {
    const at = entry.updated ?? entry.created ?? 0;
    const days = Math.floor((start - at) / 86_400_000) + 1;
    const [heading] = GROUPS.find(([, inside]) => inside(days)) ?? GROUPS[GROUPS.length - 1];
    if (!out.has(heading)) out.set(heading, []);
    out.get(heading).push(entry);
  }
  return [...out.entries()];
}
