"""Saved conversations: what the shelf keeps, and what comes back.

    python3 tests/test_chat_history.py

`web/creator/chatstore.js` is the room's memory — an index of every chat and
one file per chat in ComfyUI's userdata — and the room trusts it in two ways
that would fail quietly. A `pack` that dropped a field the render card draws
would reopen a chat with its pictures gone and no error; a title that was cut
mid-word, an index that lost a line on rename, a delete that left the body
behind, would each look fine on the screen that did them and wrong on the
next. So this drives the real module against the stub userdata API the other
packed suites use: save two chats, list, rename, delete, round-trip a state
with a finished card and a card left mid-render, and read what came back.

Skips itself if node is not installed.
"""

import layout
from harness import FAILURES, check, passed

layout.skip_without_node()
passed("saved chats keep their renders, their order and their names")

SCRIPT = """
const store = await import("./web/creator/chatstore.js");
const out = {};

// -- titles -----------------------------------------------------------------
out.titles = {
  short: store.titleFor("a fox in a snowy wood at dusk"),
  attached: store.titleFor("this coat, but red\\n(attached: @pic-1)"),
  long: store.titleFor("a very long opening line that goes on well past the width of any sidebar row anyone would draw"),
  spaces: store.titleFor("  two   words  "),
  empty: store.titleFor(""),
};

// -- one conversation, packed and back --------------------------------------
const done = {
  action: { act: "render", kind: "still", prompt: "a fox", aspect: "16:9" },
  state: "done", progress: 1, promptId: "p1", frameUrl: "blob:gone", stop: () => {},
  saved: { filename: "Krea2_00001_.png", subfolder: "continuity/stills/krea2", type: "output" },
  isClip: false, piece: { version: 1 },
  entry: { handle: "pic-1", kind: "still", aspect: "16:9", turn: 1,
           filename: "continuity/stills/krea2/Krea2_00001_.png [output]", text: "a fox" },
};
const left = { action: { act: "render", kind: "video", prompt: "she looks up" },
               state: "running", progress: 0.4, promptId: "p2", home: { messages: [] } };
const state = {
  messages: [
    { role: "assistant", say: "Which family?", local: true },
    { role: "user", text: "a fox", attached: [], turn: 1 },
    { role: "assistant", say: "Making it now.", action: done.action, card: done },
    { role: "user", text: "now a clip", attached: [], turn: 2 },
    { role: "assistant", say: "Five seconds.", action: left.action, card: left },
  ],
  ledger: [done.entry], counts: { pic: 1, clip: 0, snd: 0 }, turn: 2,
  piece: { subjects: [{ handle: "anna", takes: "person", from: ["img-1"] }],
           assets: [{ handle: "img-1", kind: "image", role: "reference", filename: "anna.png" }],
           family: "not kept" },
};
const packed = store.pack(state);
out.packed = {
  messages: packed.messages.length,
  localDropped: packed.messages.every((m) => !m.local),
  doneCard: packed.messages[1].card,
  leftCard: packed.messages[3].card,
  json: JSON.stringify(packed).length < 2000,
};
const back = store.unpack(JSON.parse(JSON.stringify(packed)));
out.back = { turn: back.turn, counts: back.counts, ledger: back.ledger.length,
             turns: back.messages.filter((m) => m.role === "user").map((m) => m.turn),
             saved: back.messages[1].card.saved, entry: back.messages[1].card.entry.handle,
             leftState: back.messages[3].card.state,
             piece: back.piece };
out.cover = store.coverOf(state);
out.emptyPiece = store.unpack({ messages: [], ledger: [], counts: {}, turn: 0 }).piece;

// -- a planned piece ---------------------------------------------------------
// The plan lives on the message whose card draws it. Its document and the
// doubts planning kept come back; an edit in flight and the sentence a
// refused one was said in were the moment's.
const doc = { version: 1, title: "The Bottle", seconds: 12, beats: [], entities: [], shots: [] };
const planned = store.pack({ messages: [
  { role: "user", text: "a 12 s piece about a bottle", attached: [], turn: 1, brief: true },
  { role: "assistant", say: "Day or night?", planAsk: { brief: "a 12 s piece about a bottle" } },
  { role: "user", text: "night", attached: [], turn: 2, brief: true },
  { role: "assistant", say: "A plan.", plan: { doc, warnings: ["shots.b1: a doubt"],
                                               pending: true, error: "refused" } },
], ledger: [], counts: {}, turn: 2 });
const replanned = store.unpack(JSON.parse(JSON.stringify(planned)));
out.plan = { brief: replanned.messages[0].brief, ask: replanned.messages[1].planAsk,
             plan: replanned.messages[3].plan, plain: "plan" in planned.messages[1] };

// -- the shelf --------------------------------------------------------------
const t0 = 1_700_000_000_000;
const a = { id: "a", title: "", created: t0 };
const b = { id: "b", title: "", created: t0 + 1000 };
const lineA = await store.saveChat(a, state, t0 + 10);
const lineB = await store.saveChat(b, { messages: [{ role: "user", text: "a lighthouse in a storm" }],
                                       ledger: [], counts: {}, turn: 1 }, t0 + 20);
out.lines = { a: lineA, b: lineB };
out.listed = (await store.listChats()).map((e) => e.id);
out.renamed = await store.renameChat("a", "  The fox   chat ");
out.renamedBlank = await store.renameChat("a", "   ");
out.afterRename = (await store.listChats()).map((e) => [e.id, e.title]);
// Saving A again keeps its name and moves it to the top.
const again = await store.saveChat({ ...a, title: "The fox chat" }, state, t0 + 30);
out.again = { title: again.title, order: (await store.listChats()).map((e) => e.id) };
out.loaded = (await store.loadChat("a"))?.messages.length;
await store.deleteChat("a");
out.afterDelete = { listed: (await store.listChats()).map((e) => e.id),
                    body: await store.loadChat("a"),
                    files: [...globalThis.__userdata.keys()].sort() };

// -- days -------------------------------------------------------------------
const noon = new Date(2026, 8, 16, 12).getTime();
const day = 86_400_000;
const grouped = store.groupByDay([
  { id: "now", updated: noon - 3600e3 },
  { id: "early", updated: new Date(2026, 8, 16, 0, 5).getTime() },
  { id: "yday", updated: new Date(2026, 8, 15, 23, 50).getTime() },
  { id: "week", updated: noon - 5 * day },
  { id: "old", updated: noon - 40 * day },
], noon);
out.grouped = grouped.map(([h, es]) => [h, es.map((e) => e.id)]);

console.log(JSON.stringify(out));
"""

with layout.pack(skip=["atlas*"]) as target:
    out = layout.in_pack(SCRIPT, target)

titles = out["titles"]
check("a short line is the title as typed", bool(titles["short"] == "a fox in a snowy wood at dusk"), True)
check("the attachment note is not part of the title", bool(titles["attached"] == "this coat, but red"), True)
check(f"a long line is cut at a word, got {titles['long']!r}", bool(titles["long"].endswith("…") and len(titles["long"]) <= 50
      and not titles["long"].rstrip("…").endswith(" ")), True)
check("runs of spaces collapse", bool(titles["spaces"] == "two words"), True)
check("nothing said is no title", bool(titles["empty"] == ""), True)

packed = out["packed"]
check("the room's own bubbles are not saved", bool(packed["messages"] == 4 and packed["localDropped"]), True)
card = packed["doneCard"]
check(f"a finished card keeps what draws it: {card}", bool(card["state"] == "done" and card["saved"]["filename"] == "Krea2_00001_.png"
      and card["entry"]["handle"] == "pic-1" and card["isClip"] is False), True)
check("the moment's fields — preview frame, listener, progress — are not saved", bool("frameUrl" not in card and "stop" not in card and "progress" not in card), True)
check(f"a card mid-render is saved as left, with its prompt id: {packed['leftCard']}", bool(packed["leftCard"]["state"] == "left" and packed["leftCard"]["promptId"] == "p2"
      and "home" not in packed["leftCard"]), True)
check("the packed conversation is small", bool(packed["json"]), True)

back = out["back"]
check(f"turn, counters and ledger round-trip: {back}", bool(back["turn"] == 2 and back["counts"] == {"pic": 1, "clip": 0, "snd": 0} and back["ledger"] == 1), True)
check("a user message keeps the turn it was said on, so the chat can be cut back to it",
      back["turns"], [1, 2])
check("the chat's own piece comes back as its cast and their files, and nothing else",
      back["piece"], {"subjects": [{"handle": "anna", "takes": "person", "from": ["img-1"]}],
                      "assets": [{"handle": "img-1", "kind": "image", "role": "reference",
                                  "filename": "anna.png"}]})
check("a chat saved before it had a piece comes back with an empty one",
      out.get("emptyPiece"), {"subjects": [], "assets": []})
check(f"cards come back whole: {back}", bool(back["saved"]["subfolder"] == "continuity/stills/krea2" and back["entry"] == "pic-1"
      and back["leftState"] == "left"), True)
plan = out["plan"]
check("a brief comes back a brief", plan["brief"], True)
check("the brief's questions come back with the brief they asked about",
      plan["ask"], {"brief": "a 12 s piece about a bottle"})
check("a plan comes back with its document and its doubts, and nothing of the moment",
      plan["plan"], {"doc": {"version": 1, "title": "The Bottle", "seconds": 12, "beats": [],
                             "entities": [], "shots": []}, "warnings": ["shots.b1: a doubt"]})
check("a message with no plan saves none", plan["plain"], False)
check(f"the cover is the last render: {out['cover']}", bool(out["cover"] == {"cover": "continuity/stills/krea2/Krea2_00001_.png [output]", "coverKind": "still"}), True)

lines = out["lines"]
check(f"the index line is built from the state: {lines['a']}", bool(lines["a"]["title"] == "a fox" and lines["a"]["renders"] == 1
      and lines["a"]["cover"].endswith("[output]") and lines["a"]["updated"] == 1_700_000_000_010), True)
check(f"a chat with no render has no cover: {lines['b']}", bool(lines["b"]["title"] == "a lighthouse in a storm" and lines["b"]["renders"] == 0
      and lines["b"]["cover"] is None), True)
check(f"newest first: {out['listed']}", bool(out["listed"] == ["b", "a"]), True)
check(f"rename trims and collapses: {out['renamed']}", bool(out["renamed"]["title"] == "The fox chat"), True)
check("a blank name is refused", bool(out["renamedBlank"] is None), True)
check(f"rename touches one line: {out['afterRename']}", bool(out["afterRename"] == [["b", "a lighthouse in a storm"], ["a", "The fox chat"]]), True)
check(f"saving again keeps the name and moves the chat up: {out['again']}", bool(out["again"] == {"title": "The fox chat", "order": ["a", "b"]}), True)
check("the body loads back", bool(out["loaded"] == 4), True)
after = out["afterDelete"]
check(f"delete removes the body and the line: {after}", bool(after["listed"] == ["b"] and after["body"] is None
      and after["files"] == ["continuity.chat.b.json", "continuity.chats.json"]), True)

check(f"days are the calendar's: {out['grouped']}", bool(out["grouped"] == [["Today", ["now", "early"]], ["Yesterday", ["yday"]],
                         ["Earlier this week", ["week"]], ["Older", ["old"]]]), True)
