"""The two shapes the chat room and the chat server agree about in silence.

    python3 tests/test_chat_mirror.py

Everything else between the room and `creator/chat.py` fails loudly: a bad
action is a sentence naming the field, a blob the compiler will not take is a
refusal in a bubble. Two things do not.

**A handle's prefix is how the server knows what a file is.** `chat._media_kind`
reads `img-3` as a picture and `vid-1` as a clip — there is no `kind` beside it
in the action, and there cannot be, because the model writes the handle and
nothing else. So a room that minted `pic-3` would send a citation the compiler
refuses with a sentence about a handle nobody recognises, for a file that is
sitting right there.

**A ledger entry is read field by field.** `ledger_line` draws the line the
model reads and `_cited` opens the file behind it; a room that wrote `file`
where the server reads `filename` would produce a ledger that looks right on
screen, reads as a row of bare handles to the model, and refuses every citation
as a thing with no file behind it.

Both are one word each, in two languages, and neither has a test that would go
red. This is that test. It reads the source rather than running it, the way
`test_js_links.py` does: what is being held together is two spellings, and
spelling is visible in the text.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import layout  # noqa: E402
from harness import FAILURES, check, passed  # noqa: E402

chat = layout.load("prompting", "chat").chat

with open(layout.js("chat.js"), encoding="utf-8") as handle:
    ROOM = handle.read()
with open(layout.js("chatmodel.js"), encoding="utf-8") as handle:
    THINKER = handle.read()


# ---- the handle prefixes ------------------------------------------------------

block = re.search(r"const PREFIX = \{([^}]*)\}", ROOM)
if not block:
    FAILURES.append("chat.js no longer declares a PREFIX table")
    room_prefixes = {}
else:
    room_prefixes = dict(re.findall(r'(\w+)\s*:\s*"([^"]+)"', block.group(1)))

# The server's half is a real dict in a real function, so it is read by asking
# rather than by grepping: every prefix the room can mint has to come back as
# the media kind the room minted it for.
for media, prefix in sorted(room_prefixes.items()):
    try:
        got = chat._media_kind(f"{prefix}-1")
    except chat.ActionError as problem:
        FAILURES.append(f"the room mints {prefix}-1 and the server refuses it: {problem}")
        continue
    check(f"{prefix}-N is a {media} on both sides", got, media)

check("the room mints a handle for every kind the server accepts",
      sorted(room_prefixes.values()), ["clip", "pic", "snd"])


# ---- the ledger entry ---------------------------------------------------------

# What the room writes, off the one call that writes it. Shorthand properties
# count: `filename` and `{filename: filename}` are the same field, and the one
# this would miss is the one a room actually writes.
written = re.search(r"const entry = \{ handle:(.*?)\};", ROOM, re.DOTALL)
room_keys = (set(re.findall(r"(?:^|[,{])\s*(\w+)\s*(?=[:,}])", written.group(0)))
             if written else set())
check("the room writes the six fields a ledger line is made of",
      sorted(room_keys),
      ["aspect", "filename", "handle", "kind", "text", "turn"])

# And what the server reads, asked the only way that cannot go stale: hand it an
# entry and see whether the line comes out whole.
entry = {"handle": "img-3", "kind": "still", "aspect": "16:9", "turn": 4,
         "filename": "continuity/chat/img-3.png [output]",
         "text": "a fox on a snowy ridge at dusk"}
check("an entry the room would write reads back as the spec's line",
      chat.ledger_line(entry),
      'img-3 · still · 16:9 · turn 4 · "a fox on a snowy ridge at dusk"')
check("and the file behind it is the one the room uploaded",
      chat._cited({"from": ["img-3"]}, [entry]),
      [("img-3", "image", "continuity/chat/img-3.png [output]", None)])

# A field spelled wrong is exactly the silent failure above: the line still
# draws, and the citation still refuses.
missing = dict(entry)
missing.pop("filename")
try:
    chat._cited({"from": ["img-3"]}, [missing])
    FAILURES.append("an entry with no filename was accepted")
except chat.ActionError:
    pass


# ---- the verbosity dial -------------------------------------------------------
#
# The rail's dial is a number from 0 to 1 that the server cuts into `chat.TIERS`
# blocks of prompting. The room names the same count so the readout beside the
# slider says which block a position lands in, and sends the number on the
# turn's settings block, where the route reads it by name.

tiers = re.search(r"const VERBOSITY_TIERS = (\d+)", THINKER)
check("the room cuts the dial into as many blocks as the server",
      tiers and int(tiers.group(1)), chat.TIERS)
block = re.search(r"function requestBlock\(.*?\n\}", ROOM, re.DOTALL)
check("the turn's settings block carries the dial",
      bool(block) and "verbosity:" in block.group(0), True)
check("and the rail starts at the bottom of it",
      bool(re.search(r"function defaultRail\(.*?verbosity: 0,.*?\n\}", ROOM, re.DOTALL)), True)
with open(os.path.join(layout.PY_ROOT, "routes", "chat.py"), encoding="utf-8") as handle:
    ROUTE = handle.read()
check("the route hands the dial to the system prompt by the same name",
      'verbosity=block.get("verbosity")' in ROUTE, True)

# ---- the reply budget ---------------------------------------------------------
#
# The rail's own token budget for a turn, apart from the refiner's rewrite
# budget: the room starts it where the server defaults it, offers the pill
# between the server's ends, sends it on the settings block, and the route
# clamps it there rather than reading the refiner's `max_tokens`.
check("the rail starts the reply budget at the server's default",
      bool(re.search(r"function defaultRail\(.*?reply_tokens: %d,.*?\n\}" % chat.REPLY_TOKENS, ROOM, re.DOTALL)), True)
check("the turn's settings block carries it",
      bool(block) and "reply_tokens:" in block.group(0), True)
ends = re.search(r"const REPLY_TOKENS = \{ min: (\d+), max: (\d+)", THINKER)
check("the pill's ends are the server's clamp",
      ends and (int(ends.group(1)), int(ends.group(2))), (chat.MIN_REPLY_TOKENS, chat.MAX_REPLY_TOKENS))
check("the route spends the rail's budget, clamped, not the refiner's",
      'max_tokens=chat.reply_tokens(block.get("reply_tokens"))' in ROUTE, True)
check("junk falls back to the default, and the ends hold",
      [chat.reply_tokens(v) for v in (None, "x", 0, 1024, 10 ** 6)],
      [chat.REPLY_TOKENS, chat.REPLY_TOKENS, chat.MIN_REPLY_TOKENS, 1024, chat.MAX_REPLY_TOKENS])


# ---- the node's id ------------------------------------------------------------
#
# The chat prompt's one node is keyed by something no canvas node can be
# called, or ComfyUI files the render on whichever node is. The room does not
# spell the id — a card follows its render by prompt id, and the previewer's
# own node name is not to be trusted (chat.js, `kj_preview_override`).

check("the chat's node is not a canvas node's id", chat.NODE.isdigit(), False)


# ---- the conversation ---------------------------------------------------------
#
# The room sends its own transcript, so what it calls a turn has to be what
# `chat.context` reads one as. Held here by building the message the room builds
# and reading the block back.

message = chat.context(
    [{"role": "user", "text": "a fox in a snowy wood at dusk"},
     {"role": "assistant", "say": "Making it now.",
      "action": {"act": "render", "kind": "still", "prompt": "a red fox at dusk",
                 "from": [], "seconds": None, "aspect": None, "say": "Making it now."}},
     {"role": "user", "text": "now a clip of it"}],
    [entry], "WHAT THIS MACHINE MAKES")
check("a user turn reads back as what was said",
      "user: a fox in a snowy wood at dusk" in message, True)
check("an assistant turn reads back as the action it took",
      '"prompt": "a red fox at dusk"' in message, True)
check("and the ledger the room keeps is the block the model is given",
      chat.ledger_line(entry) in message, True)

passed("the room and the server spell handles and ledger entries the same way")
