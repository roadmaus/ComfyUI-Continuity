"""Director's planning calls: what the model is asked, in what words, and the
loop that turns its answers into a plan.

`director.py` is the half of a plan that is not a model. This is the other
half, kept just as pure: no ComfyUI, no disk beyond the prompt files, and no
transport. The model is reached through an `ask` callable the caller hands in
— `routes/director.py` will hand in `routes/chat._ask`, `tools/director_bench.py`
hands in `refine_remote.chat` with a stopwatch round it — so the code that
plans a piece in the room is byte for byte the code the bench measured.

**One decision per call.** A plan is filled in five kinds of call: the brief
(is anything blocking?), the basics (title and look), the beats, the
entities, and the shots, one call per beat. A sixth, the turn, reads what the
person says about a plan once it exists (see "plan turns" below). Each answers one small object
against a fixed schema. That is the bargain `chat.py` already makes, and for
the same reason: a 2B model holding one question gets it right far more often
than one holding five, and a wrong answer to a small question is a cheap
re-ask rather than a wasted plan.

**Code tells the model the numbers it would otherwise guess.** How many beats
a piece of this length wants, and how many shots a beat of this many seconds
can hold, are counted here and written into the message as an instruction.
The model is still free to answer differently — the readers take anything in
range — but a small model told "write 4 beats" writes four, and a small model
told "a 40-second film" writes anything from two to eleven.

**What the model says about seconds is overruled when the person said.**
`asked_seconds` reads a length out of the brief ("a 40-second spot", "15 s");
when there is one, it wins over the basics call's number, because it was a
decision and the model's was a guess.

**The prompt files are stable wording, never assembled.** One file per call
under `prompts/director/`, each with one worked example, read once. What
varies — the brief, the names, the beat being written — goes in the user
message, in a fixed order that ends with the instruction, the order
`chat.context` uses and for its reason: what a small model read last is what
it is still holding when it starts writing.

**One re-ask, then a sentence.** A reply that does not parse, or that a
`director` reader refuses, is sent back once with the refusal quoted, as the
chat does. A second failure stops planning with `PlanningFailed`, which keeps
the plan as far as it got — degrade, don't discard: the beats that worked are
still the person's to look at.

**Two shapes of the same plan.** Everything above is the shape built for the
2B floor and measured against it (§12.1 of the spec): each call is shown a
sliver, because the floor model copies whatever it is shown and writes
whichever beat it read first. A model that holds a whole brief at once pays
for that shape in what no sliver can see — the shot that opens beat 3 is
joined to beat 2 by a model that never read beat 2's shots — and in a dozen
sequential round trips. So the room has a planning setting with two values
(`STEPS`): `small`, the calls above, and `large`, two calls — the
**structure** (header, beats and entities in one object) and the **shot
list** for the whole piece, with every beat and its seconds in view. Same
readers, same schemas' vocabulary, same one re-ask, same plan document;
only what the model is shown and asked at once differs. Small is the
default because it holds on every model; large is for the one the person
knows can carry it, and `tools/director_bench.py --steps large` is how they
find out.

**A shot is written knowing where it sits.** The small shots call was once
shown its own beat and nothing round it, and so chose how the beat joins the
one before without having read it. It is shown the beat on either side now,
as beats — what happens, never the shots written for it, which the floor
model copies — and the choices the piece was planned on. What it still cannot
know, code checks: a first shot that says it carries on from a shot set
somewhere else is a real cut (`_joined`).

**A scene says where it is once.** The shot that opens a scene (`new`) writes
a `setting`, one line of place, time and light; code carries it, and the
scene's place, into every shot of the scene (`director.scenery`), so a second
angle is not sampled with no room to be in.

**A shot too long for one clip is written apart.** Code cuts it
(`director.clips`); the **parts** call then asks what happens in each clip,
in order, so the second clip is not handed the whole shot's sentence to play
again from its start. A parts call that fails costs the plan nothing: the
shot keeps its one sentence and the wording says which part each clip is
(`director.PART`).
"""

import copy
import os
import re
import unicodedata

from . import director
from .families import refine


_PROMPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts", "director")

CALLS = ("brief", "basics", "beats", "entities", "shots", "parts")

# How many calls a plan is made in (the module header). Read off the room's
# rail by `steps_of`; anything that is not "large" is small, so a rail saved
# before the setting existed plans as it always did.
SMALL, LARGE = "small", "large"
STEPS = (SMALL, LARGE)

_read = {}


def steps_of(value):
    """The room's planning setting -> `SMALL` or `LARGE`."""
    return LARGE if str(value or "").strip().lower() == LARGE else SMALL


def prompt_file(name):
    """One call's system prompt, read once and held."""
    if name not in _read:
        with open(os.path.join(_PROMPTS, f"{name}.txt"), "r", encoding="utf-8") as handle:
            _read[name] = handle.read().strip()
    return _read[name]


class Doubt(director.PlanError):
    """A reply that is usable but probably not what was meant — a shot that
    repeats an earlier one. Re-asked like any refusal; if the re-ask has the
    same doubt, the reply is kept and the sentence becomes a warning the
    card shows, because a plan with one weak shot is still the person's to
    fix, and a plan thrown away over it is not."""

    def __init__(self, sentence, value):
        super().__init__(sentence)
        self.value = value


class PlanningFailed(RuntimeError):
    """A call failed twice. Carries the sentence, the plan as far as it got,
    and the log, so the room can show what worked and say what did not."""

    def __init__(self, sentence, plan, log):
        super().__init__(sentence)
        self.plan = plan
        self.log = log


# ---- schemas -------------------------------------------------------------------

# Sent with the call where the backend enforces one (Ollama's and OpenAI's
# `response_format`). Loose on purpose — no `additionalProperties: false`, no
# lengths — because a grammar that refuses a stray field makes some servers
# loop, and every rule that matters is the reader's, which quotes the problem
# back on a re-ask. The schema's job is only to make the reply an object of
# roughly the right shape.
def _list_of(properties, required):
    return {"type": "array", "items": {"type": "object", "properties": properties,
                                       "required": list(required)}}


SCHEMAS = {
    "brief": {"type": "object", "properties": {
        "questions": {"type": "array", "items": {"type": "string"}},
        "assumptions": {"type": "array", "items": {"type": "string"}}},
        "required": ["questions", "assumptions"]},
    "basics": {"type": "object", "properties": {
        "title": {"type": "string"}, "seconds": {"type": "integer"},
        "look": {"type": "string"}, "camera": {"type": "string"}},
        "required": ["title", "seconds", "look"]},
    "beats": {"type": "object", "properties": {
        "beats": _list_of({"text": {"type": "string"},
                           "weight": {"type": "string", "enum": list(director.WEIGHTS)}},
                          ("text", "weight"))},
        "required": ["beats"]},
    "entities": {"type": "object", "properties": {
        "entities": _list_of({"name": {"type": "string"},
                              "kind": {"type": "string", "enum": list(director.KINDS)},
                              "description": {"type": "string"}},
                             ("name", "kind", "description"))},
        "required": ["entities"]},
    "shots": {"type": "object", "properties": {
        "shots": _list_of({"action": {"type": "string"},
                           "continues": {"type": "string", "enum": list(director.CONTINUES)},
                           "setting": {"type": "string"}},
                          ("action", "continues"))},
        "required": ["shots"]},
    "parts": {"type": "object", "properties": {
        "parts": {"type": "array", "items": {"type": "string"}}},
        "required": ["parts"]},
}

# The large profile's two calls: the brief, basics, beats and entities calls'
# fields in one object, and the shots call's with the beat each shot shows.
SCHEMAS["structure"] = {"type": "object", "properties": {
    **SCHEMAS["brief"]["properties"], **SCHEMAS["basics"]["properties"],
    **SCHEMAS["beats"]["properties"], **SCHEMAS["entities"]["properties"]},
    "required": ["questions", "assumptions", "title", "seconds", "look", "beats", "entities"]}
SCHEMAS["shotlist"] = {"type": "object", "properties": {
    "shots": _list_of({"beat": {"type": "integer"}, "action": {"type": "string"},
                       "continues": {"type": "string", "enum": list(director.CONTINUES)},
                       "setting": {"type": "string"}},
                      ("beat", "action", "continues"))},
    "required": ["shots"]}

LARGE_CALLS = ("structure", "shotlist")
CALLS = CALLS + LARGE_CALLS


# ---- what code counts for the model --------------------------------------------

# The length a brief asks for is read by `director.asked_seconds`, which the
# chat's turn route reads too, to know a request is longer than one shot.
asked_seconds = director.asked_seconds


def one_take(plan):
    """Whether the brief asks for the piece as one unbroken shot: then it is
    one beat of one shot, and that shot is a take (`director.asks_one_take`)."""
    return director.asks_one_take(plan.get("brief"))


def beats_for(seconds):
    """How many beats to ask for: one for a single shot's length, then about
    one per ten seconds, within the reader's range."""
    if seconds <= 8:
        return 1
    return max(2, min(director.MAX_BEATS, int(round(seconds / 10.0))))


def shots_for(seconds):
    """The most shots to ask of a beat this long: about one per five seconds,
    one to four. A beat longer than four shots can hold is split by code."""
    return max(1, min(4, int(round(seconds / 5.0))))


# ---- the messages --------------------------------------------------------------

REPLY = "Answer with the JSON object in a ``` fence, and nothing after it."


def _block(title, lines):
    lines = [line for line in lines if line]
    return "\n".join([title] + lines) if lines else ""


def _message(*blocks):
    return "\n\n".join(block for block in blocks if block)


def _cast_lines(cast):
    return [f"@{m['name']} — " + (m.get("description") or "somebody already cast")
            for m in cast]


def _camera_block(plan):
    """How every shot is filmed, when the brief said (`director.read_basics`).
    Shown to every call below the basics: a piece seen through somebody's
    eyes is written as what they see from the beats down, and its writer has
    to be told so where it writes, since the brief alone did not stop a 27B
    model from opening the diver's own POV piece on the diver standing on
    the deck."""
    camera = (plan.get("camera") or "").strip()
    return _block("THE CAMERA (every shot is filmed this way)", [camera]) if camera else ""


def _ledger_lines(ledger):
    return [f"@{e['handle']} — attached {e.get('kind') or 'picture'}"
            + (f": {e['text']}" if e.get("text") else "") for e in ledger]


def brief_message(brief, cast=(), ledger=()):
    return _message(
        _block("THE BRIEF", [brief]),
        _block("CAST (already cast — use as they are)", _cast_lines(cast)),
        _block("ATTACHED", _ledger_lines(ledger)),
        "Decide whether this brief can be planned. " + REPLY)


def basics_message(brief, assumptions=(), seconds=None):
    length = (f"The person asked for {seconds} seconds." if seconds
              else f"The person named no length; use {director.DEFAULT_SECONDS}.")
    return _message(
        _block("THE BRIEF", [brief]),
        _block("ASSUMED", [f"- {a}" for a in assumptions]),
        f"Give the piece its title, length and look. {length} " + REPLY)


def beats_message(plan, cast=()):
    count = 1 if one_take(plan) else beats_for(plan["seconds"])
    many = "1 beat" if count == 1 else f"{count} beats"
    return _message(
        _block("THE BRIEF", [plan["brief"]]),
        _block("ASSUMED", [f"- {a}" for a in plan.get("assumptions") or ()]),
        _camera_block(plan),
        _block("CAST (already cast — cite with @ as written)", _cast_lines(cast)),
        f"The piece is \"{plan['title']}\", {plan['seconds']} seconds long. "
        f"Write {many} — or as many as the brief itself names, if it names them. "
        + REPLY)


def _beat_lines(plan, mark=None, seconds=None):
    out = []
    for beat in plan["beats"]:
        if beat["id"] == mark:
            out.append(f"> {beat['id']}: {beat['text']}  (THIS BEAT, about {seconds} seconds)")
        else:
            out.append(f"  {beat['id']}: {beat['text']}")
    return out


def entities_message(plan, cast=(), ledger=()):
    return _message(
        _block("THE BRIEF", [plan["brief"]]),
        _block("THE BEATS", _beat_lines(plan)),
        _camera_block(plan),
        _block("CAST (already cast — do not list them)", _cast_lines(cast)),
        _block("ATTACHED (already pictured — do not list them or what they show)",
               _ledger_lines(ledger)),
        "List the people, places and things the beats show that must look the "
        "same every time they appear. " + REPLY)


def _name_lines(plan, cast, ledger):
    described = {m["name"]: m.get("description") for m in cast}
    out = []
    for entity in plan["entities"]:
        source = entity.get("source") or {}
        if "cited" in source:
            out.append(f"@{entity['name']} — cast: "
                       + (described.get(entity["name"]) or "somebody already cast"))
        else:
            out.append(f"@{entity['name']} — {entity['kind']}: {entity['description']}")
    return out + _ledger_lines(ledger)


def shots_message(plan, beat_id, cast=(), ledger=()):
    """One beat's shots. The beat being written goes last, on its own, just
    above the instruction: shown only as a marked line in the list, a small
    model writes whichever beat it read first.

    The shot before this beat is not shown. It was, labelled "already
    written — do not repeat it", and the 2B floor model wrote it again word
    for word on most beats, and again on the re-ask. What joins one beat to
    the next is the beat text, which says what happens, and the join, whose
    wording code appends; the previous shot's prose added nothing a small
    model could use except a thing to copy."""
    seconds = beat_seconds(plan).get(beat_id)
    count = 1 if one_take(plan) else shots_for(seconds)
    order = [b["id"] for b in plan["beats"]]
    before = [s for s in plan["shots"] if order.index(s["beat"]) < order.index(beat_id)]
    at = order.index(beat_id)
    beat = plan["beats"][at]
    many = "1 shot" if count == 1 else f"1 to {count} shots"
    # The beats on either side, as beats: what has just happened and what
    # happens next is what a join is chosen on, and a beat's sentence is not
    # a shot to copy.
    around = _block("AROUND THIS BEAT (they have shots of their own — do not show them)", [
        f"just before: {plan['beats'][at - 1]['text']}" if at else "",
        f"straight after: {plan['beats'][at + 1]['text']}" if at + 1 < len(order) else ""])
    return _message(
        _block("THE PIECE", [f"\"{plan['title']}\": {plan['brief']}"]),
        _block("ASSUMED", [f"- {a}" for a in plan.get("assumptions") or ()]),
        _camera_block(plan),
        _block("NAMES you may cite", _name_lines(plan, cast, ledger)),
        around,
        _block(f"THIS BEAT (about {seconds} seconds)", [beat["text"]]),
        f"Write {many} that show this beat and nothing else."
        + (" It opens the piece, so its first shot is \"new\"." if not before else "")
        + " " + REPLY)


def parts_message(plan, shot_id, count, seconds, cast=(), ledger=()):
    """One long shot, to be written as the `count` clips it is filmed in."""
    shot = next(s for s in plan["shots"] if s["id"] == shot_id)
    beat = next(b for b in plan["beats"] if b["id"] == shot["beat"])
    return _message(
        _block("THE PIECE", [f"\"{plan['title']}\": {plan['brief']}"]),
        _camera_block(plan),
        _block("NAMES you may cite", _name_lines(plan, cast, ledger)),
        _block("THE BEAT IT SHOWS", [beat["text"]]),
        _block(f"THE SHOT ({sum(seconds)} seconds, one continuous shot)", [shot["action"]]),
        f"This shot is too long for one clip, so it is filmed as {count} clips with no cut "
        f"between them, of {', '.join(str(n) for n in seconds)} seconds. Write what happens "
        f"in each clip, in order: {count} sentences. " + REPLY)


def beat_seconds(plan):
    """`{beat id: seconds}` as the beats stand, before any shots exist: the
    share each beat will get, which is what the shots call is told."""
    beats = plan["beats"]
    shares = director.allot(int(plan["seconds"]),
                            [director.WEIGHTS.get(b.get("weight"), 2) for b in beats])
    return {b["id"]: s for b, s in zip(beats, shares)}


# ---- the large profile's two messages ---------------------------------------------
#
# Ranges, not counts: the small profile tells the model "write 4 beats"
# because the floor model told "a 40-second film" writes anything from two to
# eleven. A model that can hold the brief is told what is usual and left the
# judgment, and the readers still take anything in range. What the person's
# own words decide — a length, one continuous shot — is still said as a
# decision, on both profiles.


def _length_line(seconds):
    return (f"The person asked for {seconds} seconds." if seconds
            else f"The person named no length; use {director.DEFAULT_SECONDS}.")


def _beats_line(take):
    if take:
        return "The person asked for one continuous shot: write 1 beat."
    return (f"Write {director.MIN_BEATS} to {director.MAX_BEATS} beats, as many as the piece "
            "wants: about one for every ten seconds is usual, one for a piece that is a "
            "single moment, and as many as the brief itself names when it names them.")


def structure_message(brief, cast=(), ledger=(), seconds=None, take=False, questions=True):
    asking = ("" if questions else
              " Ask nothing: the person has answered, so plan it and write your choices as assumptions.")
    return _message(
        _block("THE BRIEF", [brief]),
        _block("CAST (already cast — use as they are, cite with @ as written, do not list them)",
               _cast_lines(cast)),
        _block("ATTACHED (already pictured — do not list them or what they show)",
               _ledger_lines(ledger)),
        "Plan the piece: its title, length, look and camera, its beats, and the people, "
        f"places and things that must look the same every time they appear.{asking} "
        f"{_length_line(seconds)} {_beats_line(take)} " + REPLY)


def restructure_message(plan, change, there=(), ledger=(), seconds=None):
    """The structure call for a replan: the piece as it stands, the change,
    and everybody the plan already holds, who are kept and not listed again."""
    length = (f"The person asked for {seconds} seconds." if seconds
              else f"Keep {plan['seconds']} seconds unless the change says otherwise.")
    return _message(
        _block("THE BRIEF", [plan["brief"]]),
        _block("THE PIECE NOW", [_now_line(plan)]),
        _block("ALREADY THERE (keep them, cite with @ as written, do not list them)",
               _cast_lines(there)),
        _block("ATTACHED (already pictured — do not list them or what they show)",
               _ledger_lines(ledger)),
        _block("THE CHANGE", [change]),
        "Plan the piece again with the change made: its title, length, look and camera, "
        "its beats, and whoever and whatever is new. Keep what the change does not "
        f"touch. Ask nothing. {length} {_beats_line(one_take(plan))} " + REPLY)


def shotlist_message(plan, cast=(), ledger=()):
    """Every beat's shots in one call. Each beat is shown with its seconds
    and how many shots it can hold, and the reply names the beat each shot
    shows by number — the card's number, never the id."""
    seconds = beat_seconds(plan)
    take = one_take(plan)
    lines = []
    for at, beat in enumerate(plan["beats"], 1):
        count = 1 if take else shots_for(seconds[beat["id"]])
        many = "1 shot" if count == 1 else f"1 to {count} shots"
        lines.append(f"beat {at} ({seconds[beat['id']]} seconds, {many}): {beat['text']}")
    return _message(
        _block("THE PIECE", [f"\"{plan['title']}\": {plan['brief']}"]),
        _block("ASSUMED", [f"- {a}" for a in plan.get("assumptions") or ()]),
        _camera_block(plan),
        _block("NAMES you may cite", _name_lines(plan, cast, ledger)),
        _block("THE BEATS", lines),
        "Write the shots of every beat, in order, each with the number of the beat it "
        "shows. A shot runs about five to fifteen seconds, and a beat's shots share its "
        "seconds. The first shot of the piece is \"new\". " + REPLY)


def reask(message, reply, sentence):
    """The same message again, with what went wrong quoted onto the end —
    `chat.reask`'s shape, for a reply that is an object and nothing else."""
    written = refine.THINK_RE.sub("", reply or "").strip()[:2400]
    return (f"{message}\n\nYour reply was:\n{written}\n\n"
            f"That cannot be used: {sentence}\n"
            "Answer again: the corrected JSON object in a ``` fence, nothing after it.")


# ---- reading the replies -------------------------------------------------------

def _object(reply):
    try:
        return refine.json_object(reply or "")
    except refine.RefineError:
        repaired = _closed(reply or "")
        if repaired is not None:
            return repaired
        raise director.PlanError(
            "your reply had no JSON object in it. Write the object in a ``` "
            "fence and nothing else.") from None


def _closed(reply):
    """An object the model forgot to close -> the object, or None.

    Without a schema the floor model writes `{"entities": [ ... ]` and stops:
    the list closed, the object not. Nothing about the meaning is in doubt,
    so the missing closers are put back — in the order the open ones need
    them, outside strings — and the result parsed. Only brackets are added;
    anything else wrong is still a re-ask.
    """
    import json

    text = refine.THINK_RE.sub("", reply).strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```\s*$", "", text).strip()
    start = text.find("{")
    if start < 0:
        return None
    text = text[start:]
    stack, quoted, escaped = [], False, False
    for char in text:
        if quoted:
            escaped = char == "\\" and not escaped
            if char == '"' and not escaped:
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char in "{[":
            stack.append("}" if char == "{" else "]")
        elif char in "}]":
            if not stack or stack.pop() != char:
                return None
    if quoted or not stack:
        return None
    try:
        data = json.loads(text + "".join(reversed(stack)))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def read_brief(raw):
    """-> `(questions, assumptions)`. Two questions at most: a third is the
    model interviewing, and the extra ones are dropped, not refused."""
    if not isinstance(raw, dict):
        raise director.PlanError('the reply must be an object with "questions" and "assumptions".')
    out = []
    for key in ("questions", "assumptions"):
        items = raw.get(key) or []
        if isinstance(items, str):
            items = [items]
        if not isinstance(items, list):
            raise director.PlanError(f'"{key}" must be a list of sentences.')
        out.append([" ".join(str(i).split())[:director.MAX_TEXT]
                    for i in items if isinstance(i, str) and i.strip()])
    return out[0][:2], out[1]


_HANDLE_RE = re.compile(r"@([A-Za-z]+-\d+)")

# A model that writes the join into the action as well as beside it.
_JOIN_TAIL_RE = re.compile(r"\s*\(?continues\s*:?\s*\"?(?:new|cut|pin)\"?\)?[\s.]*$",
                           re.IGNORECASE)


def cite_mentions(action, plan):
    """Plain mentions of an entity in a shot -> citations.

    A small model writes "the bottle glints on the rocks" about as often as
    "@bottle glints": the meaning is not in doubt, and an uncited bottle is a
    shot that never sees the bottle's sheet. So the first plain mention of
    each entity not already cited becomes its citation — "the" in front of
    it goes, as in the prompt files' own examples. Underscored names match
    with spaces ("red_boat" is "red boat"). Only the first mention: a second
    citation of one picture adds nothing the render reads.
    """
    cited = {w.lower() for w in director.CITE_RE.findall(action)}
    for entity in sorted(plan["entities"], key=lambda e: -len(e["name"])):
        name = entity["name"]
        if name in cited:
            continue
        # Matched on the accent-folded text, replaced in the real one: the
        # fold keeps every character's position, so "café" is found as
        # `cafe` and the citation lands where the word was.
        match = _mention(name).search(_fold(action))
        if match:
            action = action[:match.start()] + "@" + name + action[match.end():]
            cited.add(name)
    return action


def _fold(text):
    """Accents off, one character for one, so positions survive."""
    return "".join((unicodedata.normalize("NFKD", c).encode("ascii", "ignore").decode("ascii")
                    or c)[:1] for c in text)


def _mention(name):
    """An entity's name as words in prose: `driver_s_cab` is "driver's cab",
    `red_boat` "red boat" or "red-boat", with a "the" in front taken too."""
    words = r"[\s_'’-]+".join(re.escape(part) for part in name.split("_"))
    return re.compile(rf"(?<![@\w])(?:the\s+)?{words}\b(?!-)", re.IGNORECASE)


def mentioned(entity, text):
    """Whether the brief or the beats speak of an entity at all — by its
    name, or by any word of it four letters or longer ("keeper" for
    `lighthouse_keeper`)."""
    folded = _fold(text)
    if _mention(entity["name"]).search(folded):
        return True
    return any(re.search(rf"\b{re.escape(w)}", folded, re.IGNORECASE)
               for w in entity["name"].split("_") if len(w) >= 4)


REPEAT = 0.8
REPEAT_MIN_WORDS = 4

# Words every shot shares: what is left once these and the citations are
# gone is what the shot says happens.
_COMMON = set("""a an the and or but of in on at to from into onto over under by with
as his her their its he she they it him them is are was be this that then
while up down out off for through toward towards inside around close wide
shot medium high low angle""".split())


def _words(text):
    return {w for w in re.sub(r"[^\w@]+", " ", text.lower()).split()
            if w not in _COMMON and not w.startswith("@")}


def _check_repeats(shots, plan, beat_id):
    """A shot that mostly repeats one already in the plan, or another in the
    same reply, is refused: it is a small model copying what it was shown,
    never a piece that wants the same clip twice. "Mostly" is most of the
    shorter one's words — the copies seen on the floor model are an earlier
    shot with a framing clause added or a word swapped, which an exact match
    never catches. A `pin` that carries on writes what happens next, so it
    shares the names and little else. Compared on what is left once the
    citations and the common words are off, and only between shots that say
    at least a few things, since two four-word shots share most of
    everything."""
    seen = [(_words(s["action"]), f"shot {s['id']}") for s in plan["shots"]
            if s["beat"] != beat_id]
    for at, shot in enumerate(shots, 1):
        words = _words(shot["action"])
        for other, what in seen:
            least = min(len(words), len(other))
            if least >= REPEAT_MIN_WORDS and len(words & other) >= REPEAT * least:
                raise Doubt(f"shot {at} repeats {what} nearly word for word. Write "
                            f"what happens in this beat instead.", shots)
        seen.append((words, f"shot {at} of your reply"))
    return shots


def read_shots(raw, plan, beat_id, ledger=()):
    """The shots call -> `director.read_shots`, after code has done what it
    can: the join stripped off the action's tail, plain mentions cited, and
    citations of nobody written as plain words (a `Doubt`). Then the handles
    checked against what is attached, and repeats doubted."""
    items = raw.get("shots") if isinstance(raw, dict) else raw
    known = set(director.names(plan))
    unknown = []

    def tidy(action):
        action = cite_mentions(_JOIN_TAIL_RE.sub("", action).rstrip(" ,;"), plan)

        def plain(match):
            if match.group(1).lower() in known:
                return match.group(0)
            unknown.append(match.group(1))
            return match.group(1)
        return director.CITE_RE.sub(plain, action)

    def tidied(item):
        if not isinstance(item, dict) or not isinstance(item.get("action"), str):
            return item
        item = dict(item, action=tidy(item["action"]))
        if isinstance(item.get("setting"), str) and item["setting"].strip():
            item["setting"] = tidy(item["setting"])
        return item

    if isinstance(items, list):
        items = [tidied(i) for i in items]
    shots = _check_repeats(_check_handles(director.read_shots(items, known), ledger),
                           plan, beat_id)
    if unknown:
        # `@heart` on a small red heart: the floor model uses @ for emphasis.
        # The word is kept and the @ comes off, but only after a re-ask has
        # had the chance to say which name was meant — a typo for somebody
        # in the plan is a citation lost.
        raise Doubt(f"@{unknown[0]} is not in the plan, so it was written as a plain "
                    f"word. The names you may cite are: "
                    + ", ".join("@" + n for n in sorted(known)) + ".", shots)
    return shots


def _check_handles(shots, ledger):
    known = {e["handle"] for e in ledger}
    for at, shot in enumerate(shots, 1):
        for handle in _HANDLE_RE.findall(shot["action"]):
            if handle not in known:
                where = ", ".join("@" + h for h in sorted(known)) or "none"
                raise director.PlanError(
                    f"shot {at} cites @{handle}, which is not attached. "
                    f"The attached pictures are: {where}.")
    return shots


# ---- reading the large profile's replies -----------------------------------------


def read_structure(raw, seconds=None, known=(), questions=True, relisted=None):
    """The structure call -> `{questions, assumptions}` when it asks and may,
    else `{questions: [], assumptions, basics, beats, entities}`, each part
    read by the small profile's own reader. `known` is everybody already
    there — the cast, or on a replan every entity kept — whom the model was
    told not to list; one listed anyway is dropped and named in `relisted`."""
    if not isinstance(raw, dict):
        raise director.PlanError(
            'the reply must be one object with "questions", "assumptions", "title", '
            '"seconds", "look", "camera", "beats" and "entities".')
    asked, assumptions = read_brief(raw)
    if asked and questions:
        return {"questions": asked, "assumptions": assumptions}
    basics = director.read_basics(raw, seconds)
    beats = director.read_beats(raw.get("beats"))
    items = raw.get("entities") if isinstance(raw.get("entities"), list) else []
    listed = {director.name_of((i or {}).get("name")) for i in items if isinstance(i, dict)}
    entities = director.read_entities(raw.get("entities"), known)
    if relisted is not None:
        relisted[:] = sorted(n for n in listed if n in {str(k).lower() for k in known})
    return {"questions": [], "assumptions": assumptions, "basics": basics,
            "beats": beats, "entities": entities}


def _beat_of(beats, value, at):
    """What a shot wrote in `"beat"` -> that beat's id. The number the beats
    block showed, read loosely ("beat 2", "2", 2.0, or the id itself)."""
    text = " ".join(str(value if value is not None else "").lower().split())
    text = re.sub(r"^beat\s*(?:#|no\.?|number)?\s*", "", text)
    for beat in beats:
        if text == beat["id"]:
            return beat["id"]
    try:
        number = int(float(text))
    except ValueError:
        number = 0
    if 1 <= number <= len(beats) and float(text) == number:
        return beats[number - 1]["id"]
    raise director.PlanError(f'shot {at}\'s "beat" must be the number of the beat it shows, '
                             f"1 to {len(beats)}; it was {director._shown(value)}.")


def read_shotlist(raw, plan, ledger=()):
    """The shot list call -> `{beat id: [shots]}`, every beat with at least
    one. Each beat's shots go through `read_shots` in beat order, against the
    plan with the beats before it already written, so a repeat across beats
    is caught the way the small profile catches it. A `Doubt` on any beat is
    collected and raised once for the whole list, with the whole list as its
    value, so the one re-ask has everything to correct and a doubt kept is
    the whole plan with a warning, not one beat's shots without the rest."""
    items = raw.get("shots") if isinstance(raw, dict) else raw
    if not isinstance(items, list) or not items:
        raise director.PlanError('"shots" must be a list of {"beat", "action", "continues"} '
                                 "objects, one or more for every beat.")
    beats = plan["beats"]
    grouped = {b["id"]: [] for b in beats}
    for at, item in enumerate(items, 1):
        if not isinstance(item, dict):
            raise director.PlanError(f"shot {at} must be an object; it was {director._shown(item)}.")
        grouped[_beat_of(beats, item.get("beat"), at)].append(
            {k: v for k, v in item.items() if k != "beat"})
    empty = [at for at, b in enumerate(beats, 1) if not grouped[b["id"]]]
    if empty:
        raise director.PlanError(f"beat {empty[0]} has no shots; every beat needs at least one.")
    out, doubts, trial = {}, [], plan
    for at, beat in enumerate(beats, 1):
        try:
            shots = read_shots(grouped[beat["id"]], trial, beat["id"], ledger)
        except Doubt as doubt:
            shots = doubt.value
            doubts.append(f"beat {at}: {doubt}")
        except director.PlanError as problem:
            raise director.PlanError(f"beat {at}: {problem}") from None
        out[beat["id"]] = shots
        trial = director.set_shots(trial, beat["id"], shots)
    if doubts:
        raise Doubt(" ".join(doubts), out)
    return out


def _cited_only(plan):
    """The plan less every entity it made up that no shot cites and no sheet
    was made for -> `(plan, the names dropped)`. An entity nothing cites has
    no shot to be in and would only get a sheet rendered for nothing; a cited
    person stays, since they are the person's own."""
    cited = {w.lower() for s in plan["shots"] for w in director.CITE_RE.findall(s["action"])}
    made = director.handles_of(plan)
    kept = [e for e in plan["entities"]
            if e["name"] in cited or e["id"] in made or "cited" in (e.get("source") or {})]
    dropped = [e["name"] for e in plan["entities"] if e not in kept]
    plan = copy.deepcopy(plan)
    plan["entities"] = kept
    return plan, dropped


# ---- the loop ------------------------------------------------------------------

def _call(ask, log, name, message, read, label=None):
    """One call, with its one re-ask. -> what `read` made of the reply.

    The log entry keeps the object the model wrote (`raw`) beside what code
    made of it, which is how the bench shows a correction: the model said
    twelve seconds, the plan runs thirty. A reply that was refused is kept
    whole (`refused`), since a reply that would not parse has no object to
    keep and is exactly the one somebody tuning a prompt needs to read.
    """
    system = prompt_file(name)
    label = label or name
    entry = {"call": name, "label": label, "tries": 1, "ok": False, "error": None,
             "first_error": None, "warning": None, "raw": None}
    log.append(entry)
    reply = ask(system, message, SCHEMAS[name], label)
    try:
        entry["raw"] = _object(reply)
        value = read(entry["raw"])
        entry["ok"] = True
        return value
    except director.PlanError as problem:
        entry["first_error"] = str(problem)
        entry["refused"] = [reply]
        entry["tries"] = 2
        reply = ask(system, reask(message, reply, str(problem)), SCHEMAS[name], label)
    try:
        entry["raw"] = None
        entry["raw"] = _object(reply)
        value = read(entry["raw"])
        entry["ok"] = True
        return value
    except Doubt as doubt:
        entry["ok"] = True
        entry["warning"] = str(doubt)
        return doubt.value
    except director.PlanError as problem:
        entry["error"] = str(problem)
        entry["refused"].append(reply)
        raise


def _reader_of_entities(brief, plan, known, attached, relisted, invented):
    """The entities call's reader, with what code drops on the way: somebody
    already there (`known`: the cast, or on a replan every entity the plan
    keeps), an attached picture read as somebody, and an entity nothing in the
    brief or the beats speaks of."""
    def read(raw):
        items = raw.get("entities") if isinstance(raw, dict) else raw
        listed = {director.name_of((i or {}).get("name")) for i in items or ()
                  if isinstance(i, dict)}
        entities = director.read_entities(raw, known)
        relisted[:] = sorted(n for n in listed if n in known)
        # An attached picture listed as somebody: `@pic-1` read as a
        # person called Pic-1. It is already a picture; drop it. And an
        # entity neither the brief nor any beat speaks of has no shot to
        # be in — on the floor model, it is the prompt file's worked
        # example copied into a piece it has nothing to do with.
        told = " ".join([brief] + [b["text"] for b in plan["beats"]])
        entities = [e for e in entities if e["name"] not in attached]
        invented[:] = sorted(e["name"] for e in entities if not mentioned(e, told))
        return [e for e in entities if e["name"] not in invented]
    return read


def _joined(plan, beat_id, shots, log):
    """A beat's shots with a first join the plan cannot have, made a real cut.

    The small shots call writes how its beat joins the one before without
    having read that beat's shots. Where both shots say where they are and
    it is not the same place, "carries on" and "new angle" are both wrong —
    the camera cannot hold its position across two rooms — and the shot is
    `new`, which the log says."""
    order = [b["id"] for b in plan["beats"]]
    before = [s for s in plan["shots"] if order.index(s["beat"]) < order.index(beat_id)]
    if not before or not shots or shots[0]["continues"] == director.NEW:
        return shots
    here = {e["id"] for e in director._places(plan, shots[0]["action"])}
    there = {e["id"] for e in director._places(plan, before[-1]["action"])}
    if here and there and not here & there:
        log[-1]["overruled"] = f"{shots[0]['continues']} -> new: another place than the shot before"
        return [{**shots[0], "continues": director.NEW}] + shots[1:]
    return shots


def _write_shots(ask, log, plan, cast, ledger, beats=None):
    """One shots call per beat, in order -> the plan with their shots."""
    for beat in list(beats if beats is not None else plan["beats"]):
        shots = _call(
            ask, log, "shots", shots_message(plan, beat["id"], cast, ledger),
            lambda raw, at=beat["id"]: read_shots(raw, plan, at, ledger),
            label=f"shots.{beat['id']}")
        plan = director.set_shots(plan, beat["id"], _joined(plan, beat["id"], shots, log))
    return plan


def with_parts(ask, log, plan, cast=(), ledger=()):
    """The plan with every shot too long for one clip written as its clips
    (`shot["parts"]`), where it is not already. -> the plan.

    One parts call per such shot. A call that fails its re-ask is not the
    plan's failure: the shot stays one sentence, each clip of it is told
    which part it is (`director.PART`), and the card is warned.
    """
    made = {}
    for clip in director.clips(plan):
        made.setdefault(clip["shot"], []).append(clip["seconds"])
    names = director.names(plan)
    for number, shot in enumerate(list(plan["shots"]), 1):
        seconds = made.get(shot["id"]) or []
        if len(seconds) < 2 or len(shot.get("parts") or []) == len(seconds):
            continue

        def read(raw, count=len(seconds)):
            items = raw.get("parts") if isinstance(raw, dict) else raw
            if isinstance(items, list):
                items = [cite_mentions(i, plan) if isinstance(i, str) else i for i in items]
            return director.read_parts(items, count, names)
        try:
            parts = _call(ask, log, "parts",
                          parts_message(plan, shot["id"], len(seconds), seconds, cast, ledger),
                          read, label=f"parts.{shot['id']}")
        except director.PlanError as problem:
            log[-1]["warning"] = (f"shot {number} is filmed in {len(seconds)} clips from one "
                                  f"description, since writing them apart failed: {problem}")
            continue
        plan = director.edit(plan, shot["id"], {"parts": parts})
    return plan


def plan_piece(brief, rail, ask, cast=(), ledger=(), keyframes=None,
               shot_limit=director.SHOT_LIMIT, questions=True, steps=SMALL):
    """A brief -> `{"plan", "questions", "log", "relisted"}`.

    `ask(system, message, schema, label) -> reply text` is the one model call.
    `cast` is `[{name, description}]`, the people the brief cites; `ledger`
    is `[{handle, kind, text}]`, the pictures it cites. With `questions` on,
    a brief call that asks something stops planning there and `plan` is
    None: the room shows the questions and the person's answer is the next
    brief. `relisted` names cast members the entities call listed anyway and
    code dropped — not wrong about the piece, but measured, since a model
    that does it is not reading the cast block. `invented` names entities
    code dropped because nothing in the brief or the beats speaks of them
    (small steps only). `uncited` names entities dropped because no shot
    cites them (large steps only: there, every shot was written with every
    entity in view, so one nothing cites is one the piece does not need).
    `warnings` are the doubts a re-ask did not clear (`Doubt`), by call.

    `steps` is the room's planning setting (`STEPS`): the small calls, or
    the large profile's two.

    Raises `PlanningFailed` when a call fails its re-ask.
    """
    log, plan = [], None
    cast = _cast(cast)
    cast_names = [m["name"] for m in cast]
    relisted, invented, uncited = [], [], []
    done = {"log": log, "relisted": relisted, "invented": invented, "uncited": uncited}

    try:
        if steps_of(steps) == LARGE:
            return _plan_large(brief, rail, ask, cast, ledger, keyframes, shot_limit,
                               questions, done)
        assumptions = []
        if questions:
            asked, assumptions = _call(ask, log, "brief", brief_message(brief, cast, ledger),
                                       read_brief)
            if asked:
                return {"plan": None, "questions": asked, "assumptions": assumptions, **done}

        seconds = asked_seconds(brief)
        basics = _call(ask, log, "basics", basics_message(brief, assumptions, seconds),
                       lambda raw: director.read_basics(raw, seconds))
        plan = director.new_plan(brief, basics, rail, cast=cast_names,
                                 assumptions=assumptions, keyframes=keyframes,
                                 shot_limit=shot_limit)

        beats = _call(ask, log, "beats", beats_message(plan, cast), director.read_beats)
        plan = director.add_beats(plan, beats)

        attached = {director.name_of(e["handle"]) for e in ledger or ()}
        entities = _call(ask, log, "entities", entities_message(plan, cast, ledger),
                         _reader_of_entities(brief, plan, cast_names, attached,
                                             relisted, invented))
        plan = director.add_entities(plan, entities)
        plan = _take(director.validate(_write_shots(ask, log, plan, cast, ledger)))
        plan = with_parts(ask, log, plan, cast, ledger)
    except director.PlanError as problem:
        raise PlanningFailed(str(problem), done.pop("plan", plan), log) from None
    return {"plan": plan, "questions": [], "assumptions": plan.get("assumptions") or [],
            "warnings": _warnings(log), **done}


def _take(plan):
    """"One continuous shot" is one shot that is cut only where the video
    family stops. A model that wrote more than one shot anyway has planned
    cuts the person said they did not want; that is left for the card to
    show rather than merged by code."""
    if one_take(plan) and len(plan["shots"]) == 1:
        return director.edit(plan, plan["shots"][0]["id"], {"one_take": True})
    return plan


def _plan_large(brief, rail, ask, cast, ledger, keyframes, shot_limit, questions, done):
    """`plan_piece` on the large profile: the structure, then the shot list.
    Raises `director.PlanError` for `plan_piece` to wrap, with the plan as
    far as it got on `done["plan"]`."""
    log, plan = done["log"], None
    cast_names = [m["name"] for m in cast]
    seconds = asked_seconds(brief)
    take = director.asks_one_take(brief)
    try:
        parts = _call(ask, log, "structure",
                      structure_message(brief, cast, ledger, seconds, take, questions),
                      lambda raw: read_structure(raw, seconds, cast_names, questions,
                                                 done["relisted"]))
        if parts["questions"]:
            return {"plan": None, "questions": parts["questions"],
                    "assumptions": parts["assumptions"], **done}
        plan = director.new_plan(brief, parts["basics"], rail, cast=cast_names,
                                 assumptions=parts["assumptions"], keyframes=keyframes,
                                 shot_limit=shot_limit)
        plan = director.add_beats(plan, parts["beats"])
        attached = {director.name_of(e["handle"]) for e in ledger or ()}
        plan = director.add_entities(plan, [e for e in parts["entities"]
                                            if e["name"] not in attached])
        plan = _write_shotlist(ask, log, plan, cast, ledger)
        plan, dropped = _cited_only(plan)
        done["uncited"][:] = dropped
        plan = _take(director.validate(plan))
        plan = with_parts(ask, log, plan, cast, ledger)
    except director.PlanError:
        done["plan"] = plan
        raise
    return {"plan": plan, "questions": [], "assumptions": plan.get("assumptions") or [],
            "warnings": _warnings(log), **done}


def _write_shotlist(ask, log, plan, cast, ledger, label="shotlist"):
    """The whole piece's shots in one call -> the plan with them."""
    grouped = _call(ask, log, "shotlist", shotlist_message(plan, cast, ledger),
                    lambda raw: read_shotlist(raw, plan, ledger), label=label)
    for beat in plan["beats"]:
        plan = director.set_shots(plan, beat["id"], grouped[beat["id"]])
    return plan


def _cast(cast):
    return [{"name": director.name_of(m["name"]), "description": m.get("description") or ""}
            for m in cast or ()]


def _warnings(log):
    return [f"{e['label']}: {e['warning']}" for e in log if e.get("warning")]


# ---- plan turns ------------------------------------------------------------------
#
# While a plan is open, what the person says in the room is about the plan
# (§5.4 of the spec). One call reads it and answers one of three things: edit
# one row, replan from the beats down, or say something back. It is shown the
# plan the way the card shows it — "beat 2", "shot 3", "@keeper" — because
# those are the words the person used, and a small model matches words it was
# shown far better than it maps "the third shot" onto an id it was not.
#
# What the edit then does is the row's own call again, shown the row and the
# change: the basics for the piece, the beats call for a beat, the entities
# call for a person, place or thing, the shots call for a shot. Same prompt
# files, same readers, same schema as the plan was written with, so an edited
# row is held to exactly what a first draft was. Code keeps what is code's: a
# length the person says wins over any the model writes, a cast member the
# person cites replaces a person with no call at all, and a picture already
# made is changed on the edit path rather than drawn again.
#
# Three more acts change which shots there are rather than what one says
# (`director.ARRANGE`): **add** a shot, **remove** a shot or a beat, **move** a
# shot. Only the add needs the model again — the shots call once more, shown
# the beat and its shots and told where the new one goes, writing the one
# shot — and the other two are bookkeeping `director` does with no call. Where
# a shot goes is a `place`: "after shot 2", "before the last shot", "in beat
# 2", "first", "last". The model writes one in its own words and code reads it
# (`placement`); and the same reader runs over the person's words first, as
# `named_rows` does for the row, since "move shot 3 before shot 1" says where
# as plainly as it says which, and a small model that answers "after shot 1"
# is wrong about something that was never in doubt.

TURN_ACTS = ("edit", "replan", "say", "add", "remove", "move")

SCHEMAS["turn"] = {"type": "object", "properties": {
    "act": {"type": "string", "enum": list(TURN_ACTS)},
    "row": {"type": "string"}, "place": {"type": "string"},
    "change": {"type": "string"}, "say": {"type": "string"}},
    "required": ["act", "row", "place", "change", "say"]}

CALLS = CALLS + ("turn",)

PIECE = "the piece"


def labels(plan):
    """`[(label, row id)]`: every row the person can name, as the card names
    it. Beats and shots by position, since that is what the card numbers;
    ids never reach the model."""
    out = [(PIECE, director.HEADER)]
    out += [(f"beat {at}", b["id"]) for at, b in enumerate(plan["beats"], 1)]
    out += [(f"shot {at}", s["id"]) for at, s in enumerate(plan["shots"], 1)]
    out += [("@" + e["name"], e["id"]) for e in plan["entities"]]
    return out


def label_of(plan, row_id):
    return next((label for label, rid in labels(plan) if rid == row_id), row_id)


_HEADER_WORDS = {PIECE, "piece", "header", "title", "look", "length", "seconds", "the title",
                 "the look", "the length", "camera", "the camera"}
_POSITION_RE = re.compile(r"^(beat|shot)\s*(?:#|no\.?|number)?\s*(\d+)$")


def row_of(plan, label):
    """What the turn call wrote in `"row"` -> a row id, or a `PlanError`
    listing what it may write. Read loosely — "Shot 3", "shot #3", "keeper"
    without its @ — since the meaning is not in doubt."""
    text = " ".join(str(label or "").lower().split())
    for name, rid in labels(plan):
        if text == name:
            return rid
    if text in _HEADER_WORDS:
        return director.HEADER
    match = _POSITION_RE.match(text)
    if match:
        rows = plan["beats"] if match.group(1) == "beat" else plan["shots"]
        at = int(match.group(2))
        if 1 <= at <= len(rows):
            return rows[at - 1]["id"]
    every = {r["id"] for key in ("beats", "entities", "shots") for r in plan[key]}
    if text in every:
        return text
    name = director.name_of(text)
    if name and any(e["name"] == name for e in plan["entities"]):
        return next(e["id"] for e in plan["entities"] if e["name"] == name)
    shown = ", ".join(f'"{name}"' for name, _ in labels(plan))
    raise director.PlanError(f'"row" must name one row of the plan: {shown}; '
                             f"it was {director._shown(label)}.")


def _plan_lines(plan, cast=()):
    """The plan as the turn call reads it: the card's rows, in the card's words."""
    seconds = director.allot_plan(plan)
    described = {m["name"]: m.get("description") for m in cast}
    out = [f"{PIECE} — {_now_line(plan)}"]
    number = 0
    for at, beat in enumerate(plan["beats"], 1):
        out.append(f"beat {at} — {beat['text']} ({seconds[beat['id']]} s)")
        for shot in (s for s in plan["shots"] if s["beat"] == beat["id"]):
            number += 1
            out.append(f"  shot {number} — {shot['action']} ({seconds[shot['id']]} s)")
    for entity in plan["entities"]:
        source = entity.get("source") or {}
        if "cited" in source:
            out.append(f"@{entity['name']} — cast: "
                       + (described.get(source["cited"]) or "somebody already cast"))
        else:
            out.append(f"@{entity['name']} — {entity['kind']}: {entity['description']}")
    return out


def turn_message(plan, text, cast=()):
    return _message(
        _block("THE PLAN", _plan_lines(plan, cast)),
        _block("THE MESSAGE", [text]),
        "Decide what the message asks of the plan. " + REPLY)


def _sentence(value):
    return " ".join(value.split())[:director.MAX_TEXT] if isinstance(value, str) else ""


def read_turn(raw, plan, text=""):
    """The turn call -> `{act, row, place, change, say}`. A change left empty
    is the person's own words, which say it as well as any rewording would.
    `place` is where an added or moved shot goes (`placement`), or None."""
    if not isinstance(raw, dict):
        raise director.PlanError('the reply must be an object with "act", "row", "change" and "say".')
    act = str(raw.get("act") or "").strip().lower()
    said = _sentence(raw.get("say"))
    if not act and said and not raw.get("row") and not raw.get("change") \
            and said.lower().rstrip(".!") != _sentence(text).lower().rstrip(".!"):
        # `{"say": "..."}` and nothing else: without a schema the floor model
        # drops the act on an answer. An answer that is the message said
        # back is not one, and is re-asked.
        act = "say"
    if act not in TURN_ACTS:
        raise director.PlanError('"act" must be edit, replan, say, add, remove or move; '
                                 f'it was {director._shown(raw.get("act"))}.')
    change, say = _sentence(raw.get("change")), _sentence(raw.get("say"))
    out = {"act": act, "row": None, "place": None, "change": change or _sentence(text), "say": say}
    if act == "say":
        if not (say or change):
            raise director.PlanError('a "say" reply needs "say": the sentence to answer with.')
        return {**out, "change": "", "say": say or change}
    if act == "replan":
        return out
    if act == "add":
        # Where it goes: the place, or failing that the row it was written
        # against — a beat is its end, a shot is after it.
        place = placement(plan, raw.get("place"))
        if place is None and raw.get("row"):
            try:
                row = row_of(plan, raw.get("row"))
            except director.PlanError:
                row = None
            if row and row.startswith("b"):
                place = {"beat": row}
            elif row and row.startswith("s"):
                place = {"after": row}
        return {**out, "place": place}
    row = row_of(plan, raw.get("row"))
    if act == "remove":
        if row[0] not in "bs":
            raise director.PlanError(
                f'only a shot or a beat can be taken out; {label_of(plan, row)} is not one. '
                f'Change the shots instead.')
        return {**out, "row": row}
    if act == "move":
        if not row.startswith("s"):
            raise director.PlanError(f'only a shot can be moved; {label_of(plan, row)} is not one.')
        return {**out, "row": row, "place": placement(plan, raw.get("place"))}
    entity = next((e for e in plan["entities"] if e["id"] == row), None)
    if entity and "cited" in (entity.get("source") or {}) and not _cites_cast(text, entity):
        # Somebody the person cast is used as they are, so their row has
        # nothing to change; on the floor model it is the row picked for "he"
        # in a message about a shot.
        raise director.PlanError(
            f"@{entity['name']} is from the cast and is used as they are, so their row "
            f"cannot change. Pick the row the message is about.")
    return {**out, "row": row}


def _cites_cast(text, entity):
    """Whether `text` cites a cast member other than the one `entity` is —
    "use @anna for @george" is a recast, which code does."""
    return any(w.lower() != entity["source"]["cited"] for w in director.CITE_RE.findall(text or ""))


# ---- what the person's words say plainly ------------------------------------------
#
# Read by code, as `asked_seconds` reads a length out of a brief, and for the
# same reason: "the last beat" names one row and "make it 20 seconds" names
# one number, and a small model that answers "shot 4" to the first is wrong
# about something that was never in doubt. Each overrules the turn call only
# where the words are unambiguous, and the log says it did.

_ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
             "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10}
_NAMED_ROW_RE = re.compile(
    r"\b(?:(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|last|\d+)"
    r"(?:st|nd|rd|th)?\s+(beat|shot)s?|(beat|shot)\s*(?:#|no\.?|number)?\s*(\d+))\b",
    re.IGNORECASE)


_NAMED_LIST_RE = re.compile(r"\b(beat|shot)s\s+(\d+(?:\s*(?:,|and|&)\s*\d+)+)\b", re.IGNORECASE)


def named_rows(plan, text):
    """The beats and shots the person's words name by number or position ->
    their ids, in order, each once. "The last beat", "shot 3", "the 2nd
    shot", "shots 2 and 3"; one past the end names nothing."""
    found = []
    for match in _NAMED_ROW_RE.finditer(text or ""):
        word, kind = (match.group(1), match.group(2)) if match.group(2) else (match.group(4), match.group(3))
        found.append((match.start(), kind, word))
    for match in _NAMED_LIST_RE.finditer(text or ""):
        for number in re.findall(r"\d+", match.group(2)):
            found.append((match.start(), match.group(1), number))
    out = []
    for _at, kind, word in sorted(found, key=lambda f: f[0]):
        rows = plan["beats" if kind.lower() == "beat" else "shots"]
        word = word.lower()
        at = len(rows) if word == "last" else _ORDINALS.get(word) or int(word)
        if 1 <= at <= len(rows) and rows[at - 1]["id"] not in out:
            out.append(rows[at - 1]["id"])
    return out


_TITLE_RE = re.compile(
    r"^\s*(?:please\s+)?(?:call|title|name|rename)\s+(?:it|this|the\s+(?:piece|film|video|plan))"
    r"\s+(?:to\s+|as\s+)?[\"“'‘]?(.+?)[\"”'’]?\s*[.!]?\s*$", re.IGNORECASE)


def asked_title(text):
    """The title the person's words give the piece ("call it Last Orders"),
    or None."""
    match = _TITLE_RE.match(text or "")
    return " ".join(match.group(1).split())[:80] if match else None


# Where a shot goes, in words: a shot named next to it, a beat it joins, or
# an end of the piece. One shot reference, two ways round — "shot 2", "the
# second shot", "the last shot" — and the same for a beat.
_ORDINAL_WORDS = "|".join(list(_ORDINALS) + ["last"])
_SHOT_REF = (r"(?:shot\s*(?:#|no\.?|number)?\s*(\d+)|(?:the\s+)?(" + _ORDINAL_WORDS
             + r"|\d+)(?:st|nd|rd|th)?\s+shot)")
_BEAT_REF = (r"(?:beat\s*(?:#|no\.?|number)?\s*(\d+)|(?:the\s+)?(" + _ORDINAL_WORDS
             + r"|\d+)(?:st|nd|rd|th)?\s+beat)")
_BETWEEN_RE = re.compile(r"\bbetween\s+(?:shots?\s+)?(\d+)\s+and\s+(?:shot\s+)?(\d+)\b", re.IGNORECASE)
_NEXT_TO_RE = re.compile(r"\b(before|ahead of|in front of|after|behind|following)\s+" + _SHOT_REF,
                         re.IGNORECASE)
_IN_BEAT_RE = re.compile(r"\b(start of|beginning of|opening|open|in|into|to|inside|within|under|end of|"
                         r"close of|closing)\s+(?:the\s+)?" + _BEAT_REF, re.IGNORECASE)
_FIRST_RE = re.compile(r"\b(?:first|(?:at|to)\s+the\s+(?:start|beginning|top|front)|open(?:s|ing)?\s+"
                       r"the\s+piece)\b(?!\s+(?:shot|beat))", re.IGNORECASE)
_LAST_RE = re.compile(r"\b(?:last|(?:at|to)\s+the\s+(?:end|back|close)|end(?:s|ing)?\s+the\s+piece)\b"
                      r"(?!\s+(?:shot|beat))", re.IGNORECASE)


def _row_at(rows, digits, word):
    word = (digits or word or "").lower()
    at = len(rows) if word == "last" else _ORDINALS.get(word) or (int(word) if word.isdigit() else 0)
    return rows[at - 1]["id"] if 1 <= at <= len(rows) else None


def placement(plan, words):
    """Words saying where a shot goes -> `{"before": shot}`, `{"after":
    shot}` or `{"beat": beat}` (its end), the keywords `director.add_shot`
    and `move_shot` take; None when the words say nothing the plan has.
    "Between shots 2 and 3" is after shot 2; "the start of beat 2" is before
    its first shot; "first" and "last" are the piece's ends."""
    text = " ".join(str(words or "").split())
    shots = plan["shots"]
    if not text or not shots:
        return None
    match = _BETWEEN_RE.search(text)
    if match:
        pair = [_row_at(shots, match.group(1), None), _row_at(shots, match.group(2), None)]
        if all(pair):
            order = [s["id"] for s in shots]
            return {"after": min(pair, key=order.index)}
    match = _NEXT_TO_RE.search(text)
    if match:
        anchor = _row_at(shots, match.group(2), match.group(3))
        if anchor:
            side = "before" if match.group(1).lower() in ("before", "ahead of", "in front of") else "after"
            return {side: anchor}
    match = _IN_BEAT_RE.search(text)
    if match:
        beat = _row_at(plan["beats"], match.group(2), match.group(3))
        if beat:
            if match.group(1).lower() in ("start of", "beginning of", "opening", "open"):
                return {"before": next(s["id"] for s in shots if s["beat"] == beat)}
            return {"beat": beat}
    if _FIRST_RE.search(text):
        return {"before": shots[0]["id"]}
    if _LAST_RE.search(text):
        return {"after": shots[-1]["id"]}
    return None


# The verbs that say which act a message is, when they open it. Read by code
# because "drop shot 3" is not an edit however the floor model reads it.
_REMOVE_RE = re.compile(r"^\s*(?:please\s+)?(?:remove|delete|drop|cut out|take out|take away|"
                        r"get rid of|lose|scrap|ditch|kill)\b", re.IGNORECASE)
_ADD_RE = re.compile(r"^\s*(?:please\s+)?(?:add|insert|include|put in|squeeze in|slip in)\b"
                     r"|\b(?:another|a new|an extra|one more|an additional|a further)\s+shot\b",
                     re.IGNORECASE)
_MOVE_RE = re.compile(r"^\s*(?:please\s+)?(?:move|put|shift|bring|reorder|swap|switch)\b", re.IGNORECASE)
_SWAP_RE = re.compile(r"^\s*(?:please\s+)?(?:swap|switch|exchange)\b", re.IGNORECASE)


def asked_act(text):
    """The act the person's opening verb names — add, remove, move — or None."""
    if _REMOVE_RE.match(text or ""):
        return "remove"
    if _ADD_RE.search(text or ""):
        return "add"
    if _MOVE_RE.match(text or ""):
        return "move"
    return None


def overrule(turn, plan, text):
    """The turn call's answer, with what the words say plainly put first ->
    `(turn, note)`; `note` says what code changed, or is None.

    A title or a length the person names, with no beat or shot named beside
    it, is the piece's header ("make shot 2 five seconds" is not a length
    for the piece). A beat or shot named alone is the row an edit or a
    removal is about. "Drop", "add" and "move" opening the message are the
    act, when the rest of the words name what they need: one row to drop, a
    shot and a place to move it to. A place said in the words is where an
    added or moved shot goes, whatever the model wrote. A question keeps its
    answer: "is 20 seconds too long?" asks nothing."""
    named = named_rows(plan, text)
    asking = text.rstrip().endswith("?")
    place = placement(plan, text)
    want = None if asking else asked_act(text)
    if want == "remove" and len(named) == 1 and (turn["act"], turn["row"]) != ("remove", named[0]):
        return {**turn, "act": "remove", "row": named[0], "place": None}, f"{turn['act']} -> remove {named[0]}"
    if want == "move":
        shots = [r for r in named if r.startswith("s")]
        row, to = None, place
        if _SWAP_RE.match(text) and len(shots) == 2 and not place:
            order = [s["id"] for s in plan["shots"]]
            first, second = sorted(shots, key=order.index)
            row, to = second, {"before": first}
        elif shots and place:
            row = shots[0]
        if row and (turn["act"], turn["row"], turn["place"]) != ("move", row, to):
            return {**turn, "act": "move", "row": row, "place": to}, f"{turn['act']} -> move {row} {_said_place(to)}"
    if want == "add" and turn["act"] in ("edit", "say", "replan"):
        return {**turn, "act": "add", "row": None, "place": place,
                "change": turn["change"] or _sentence(text)}, f"{turn['act']} -> add {_said_place(place)}"
    if turn["act"] in ("add", "move") and place and turn["place"] != place:
        return {**turn, "place": place}, f"place -> {_said_place(place)}"
    if turn["act"] in ("add", "move", "remove"):
        return turn, None
    header = asked_title(text) or (not named and asked_seconds(text) not in (None, plan["seconds"]))
    if header and not asking and want is None and turn["act"] != "replan" and turn["row"] != director.HEADER:
        was = turn["row"] or turn["act"]
        return {**turn, "act": "edit", "row": director.HEADER,
                "change": turn["change"] or _sentence(text)}, f"{was} -> header"
    if turn["act"] == "edit" and len(named) == 1 and turn["row"] != named[0]:
        return {**turn, "row": named[0]}, f"{turn['row']} -> {named[0]}"
    return turn, None


def _said_place(place):
    return " ".join(f"{k} {v}" for k, v in (place or {}).items()) or "nowhere"


def _now_line(plan):
    camera = (plan.get("camera") or "").strip()
    return (f"\"{plan['title']}\", {plan['seconds']} seconds, look: {plan.get('look') or 'none'}"
            + (f", camera: {camera}" if camera else ""))


def _keep(what):
    return (f"Rewrite {what} with the change made. Keep everything the change "
            "does not touch exactly as it is.")


def header_message(plan, change, seconds=None):
    length = (f"The person asked for {seconds} seconds." if seconds
              else f"Keep {plan['seconds']} seconds.")
    return _message(
        _block("THE BRIEF", [plan["brief"]]),
        _block("THE PIECE NOW", [_now_line(plan)]),
        _block("THE CHANGE", [change]),
        "Give the piece its title, length, look and camera. " + _keep("them") + f" {length} " + REPLY)


def beat_message(plan, beat_id, change, cast=()):
    at = next(i for i, b in enumerate(plan["beats"], 1) if b["id"] == beat_id)
    beat = plan["beats"][at - 1]
    return _message(
        _block("THE BRIEF", [plan["brief"]]),
        _block("CAST (already cast — cite with @ as written)", _cast_lines(cast)),
        _block(f"BEAT {at} NOW ({beat['weight']})", [beat["text"]]),
        _block("THE CHANGE", [change]),
        _keep("this one beat") + " Write 1 beat. " + REPLY)


def entity_message(plan, entity, change):
    return _message(
        _block("THE BRIEF", [plan["brief"]]),
        _block("NOW", [f"@{entity['name']} — {entity['kind']}: {entity['description']}"]),
        _block("THE CHANGE", [change]),
        _keep(f"@{entity['name']}") + f" List only @{entity['name']}, still a "
        f"{entity['kind']}. " + REPLY)


def shot_message(plan, shot_id, change, cast=(), ledger=()):
    shot = next(s for s in plan["shots"] if s["id"] == shot_id)
    beat = next(b for b in plan["beats"] if b["id"] == shot["beat"])
    seconds = director.allot_plan(plan)
    return _message(
        _block("THE PIECE", [f"\"{plan['title']}\": {plan['brief']}"]),
        _block("NAMES you may cite", _name_lines(plan, cast, ledger)),
        _block("THIS BEAT", [beat["text"]]),
        _block(f"THIS SHOT NOW (about {seconds[shot_id]} seconds, continues \"{shot['continues']}\")",
               [shot["action"], f"setting: {shot['setting']}" if shot.get("setting") else ""]),
        _block("THE CHANGE", [change]),
        _keep("this one shot") + " Write 1 shot. " + REPLY)


def _said(cast, text):
    """The members of `cast` that `text` cites with @."""
    named = {w.lower() for w in director.CITE_RE.findall(text or "")}
    return [m for m in cast if m["name"] in named]


def _changed(new, old, what):
    """A rewrite that is the row as it was is a `Doubt`: re-asked once with
    the change quoted, then kept with a warning. The floor model asked to
    change a row it is shown copies the row about as often as it changes
    it; the re-ask is its second chance, and a row left as it was is the
    person's to change on the card."""
    if new == old:
        raise Doubt(f"your {what} is exactly as it was. Write it with the change made.", new)
    return new


def _one(items, what):
    if len(items) != 1:
        raise director.PlanError(f"write exactly one {what}; the reply held {len(items)}.")
    return items[0]


def plan_turn(plan, text, ask, cast=(), ledger=(), steps=SMALL):
    """Something said about an open plan -> `{"plan", "act", "row", "say",
    "render", "recast", "log", "warnings"}`.

    `steps` is the room's planning setting, read by a replan: an edit to one
    row is that row's own small call on either profile, since one row is one
    decision whatever the model.

    `plan` is None in the answer when nothing changed (a `say`). `render` is
    `{row, action, mark}` when the change was to a picture already made — a
    sheet, or an opening frame — and goes down the room's edit path: the
    room queues the action as a prep render of that row, under that mark.
    `cast` is `[{name, description}]`: the chat's cast members the plan
    already uses, and any the person's words cite. Citing one the plan does
    not hold, on a person the plan would draw a sheet for, is "use @george
    for the keeper", and is done by code with no call.

    Raises `PlanningFailed` (with the plan unchanged) when a call fails its
    re-ask, or when the change cannot be made.
    """
    log = []
    cast = _cast(cast)
    plan = director.validate(plan)
    try:
        def read(raw):
            try:
                return read_turn(raw, plan, text)
            except director.PlanError:
                # A row the reply cannot have — somebody cast, or no row at
                # all — is no matter when the words name the row themselves.
                named = named_rows(plan, text)
                row = named[0] if len(named) == 1 else director.HEADER if asked_title(text) else None
                if row is None or not isinstance(raw, dict) \
                        or raw.get("act") not in ("edit", "remove", "move"):
                    raise
                return read_turn({**raw, "row": row}, plan, text)

        turn = _call(ask, log, "turn", turn_message(plan, text, cast), read)
        turn, note = overrule(turn, plan, text)
        if note:
            log[0]["overruled"] = note
        out = {"plan": None, "act": turn["act"], "row": turn["row"], "say": turn["say"],
               "render": None, "recast": None, "log": log}
        if turn["act"] == "say":
            return {**out, "warnings": _warnings(log)}
        seconds = asked_seconds(text)
        if turn["act"] == "replan":
            out["plan"] = replan(plan, turn["change"], ask, cast, ledger, seconds, log, text,
                                 steps)
        elif turn["act"] == "add":
            out.update(_add_shot(plan, turn["place"], turn["change"], ask, log, cast, ledger))
        elif turn["act"] == "remove":
            out.update(_remove_row(plan, turn["row"]))
        elif turn["act"] == "move":
            out.update(_move_shot(plan, turn["row"], turn["place"]))
        else:
            out.update(_edit_row(plan, turn["row"], turn["change"], text, ask, log,
                                 cast, ledger, seconds, steps))
        if out["plan"] is not None:
            # A shot that is now too long for one clip, or was rewritten,
            # is written as its clips again. Only clips read the parts, so a
            # prep picture's mark in `render` stands.
            out["plan"] = with_parts(ask, log, out["plan"], cast, ledger)
    except director.PlanError as problem:
        if len(log) == 1 and log[0]["call"] == "turn" and not log[0]["ok"]:
            # The turn call itself failed twice: what reaches the person is
            # what to do, not the sentence the model was re-asked with.
            problem = ("Could not tell what that changes in the plan. Name the row as "
                       "the card does (“shot 2”, “beat 1”, “@keeper”), or change it on the card.")
        raise PlanningFailed(str(problem), plan, log) from None
    return {**out, "warnings": _warnings(log)}


def _edit_row(plan, row_id, change, text, ask, log, cast, ledger, seconds, steps=SMALL):
    """One row, changed by its own call. -> the parts of `plan_turn`'s answer
    that say what happened."""
    out = {"act": "edit", "row": row_id, "render": None, "recast": None}
    if row_id == director.HEADER:
        title = asked_title(text)

        def read(raw):
            basics = director.read_basics(raw, seconds or plan["seconds"])
            if title:
                basics["title"] = title
            # A plan made before the camera has none, which reads as "".
            now = {**{k: plan.get(k) for k in basics}, "camera": plan.get("camera") or ""}
            return _changed(basics, now, "title, length, look and camera")
        basics = _call(ask, log, "basics", header_message(plan, change, seconds), read,
                       label="turn.basics")
        try:
            out["plan"] = director.edit(plan, director.HEADER, basics)
        except director.PlanError:
            if basics["seconds"] == plan["seconds"]:
                raise
            # A length the shots cannot share — six shots in five seconds —
            # is a piece to plan again at that length, not a refusal.
            out.update(act="replan", row=None,
                       plan=replan(plan, change, ask, cast, ledger, basics["seconds"], log, text,
                                   steps))
        return out

    kind = row_id.rstrip("0123456789")
    if kind == "b":
        beat = next(b for b in plan["beats"] if b["id"] == row_id)
        rewritten = _call(ask, log, "beats", beat_message(plan, row_id, change, cast),
                          lambda raw: _changed(_one(director.read_beats(raw), "beat"),
                                               {k: beat[k] for k in ("text", "weight")}, "beat"),
                          label="turn.beat")
        new = director.edit(plan, row_id, rewritten)
        if rewritten["text"] != beat["text"]:
            # What happens in the beat changed, so its shots are written again;
            # a beat that only got longer keeps them.
            new = director.validate(_write_shots(
                ask, log, new, cast, ledger, [b for b in new["beats"] if b["id"] == row_id]))
        out["plan"] = new
        return out

    if kind == "e":
        entity = next(e for e in plan["entities"] if e["id"] == row_id)
        recast = next((m["name"] for m in _said(cast, text)
                       if not any(e["name"] == m["name"] for e in plan["entities"])), None)
        if recast and entity["kind"] == "person":
            out["plan"] = director.edit(plan, row_id, {"source": recast})
            out["recast"] = recast
            return out
        if "cited" in (entity.get("source") or {}):
            raise director.PlanError(
                f"@{entity['name']} is played by @{entity['source']['cited']} from the cast, as "
                f"they are. Change them in the cast, or cite somebody else for @{entity['name']}.")

        def read(raw):
            items = director.read_entities(raw)
            got = _one(items, f"entry, @{entity['name']}")
            if got["description"] == entity["description"]:
                raise Doubt(f"your description of @{entity['name']} is exactly as it was. "
                            "Write it with the change made.", got)
            return got
        rewritten = _call(ask, log, "entities", entity_message(plan, entity, change), read,
                          label="turn.entity")
        fields = {"description": rewritten["description"]}
        # A new name only when the person said it: a small model asked to
        # change a description renames as often as not ("old_keeper").
        if rewritten["name"] != entity["name"] and _mention(rewritten["name"]).search(_fold(text)):
            fields["name"] = rewritten["name"]
        new = director.edit(plan, row_id, fields)
        out["plan"] = new
        out["render"] = _changed_picture(plan, new, row_id, change)
        return out

    shot = next(s for s in plan["shots"] if s["id"] == row_id)
    rewritten = _call(ask, log, "shots", shot_message(plan, row_id, change, cast, ledger),
                      lambda raw: _changed(_one(read_shots(raw, plan, shot["beat"], ledger), "shot"),
                                           {k: shot[k] for k in ("action", "continues", "setting")
                                            if k in shot}, "shot"),
                      label="turn.shot")
    # A scene's setting is kept unless the rewrite gives another: the change
    # was to what the shot shows.
    new = director.edit(plan, row_id, {**({"setting": shot["setting"]} if shot.get("setting") else {}),
                                       **rewritten})
    out["plan"] = new
    frame = next((r["id"] for r in director.rows(new)
                  if r["kind"] == "keyframe" and r["shot"] == row_id), None)
    out["render"] = _changed_picture(plan, new, frame, change) if frame else None
    return out


def _anchor_of(plan, place):
    """A place -> `(beat id, the shot it is next to or None, side)`."""
    if "beat" in place:
        return place["beat"], None, "at the end of"
    side = "before" if "before" in place else "after"
    anchor = next(s for s in plan["shots"] if s["id"] == place[side])
    return anchor["beat"], anchor["id"], side


def new_shot_message(plan, place, change, cast=(), ledger=()):
    """The shots call, asked for one more shot: the beat it joins with the
    shots that beat has, where the new one goes among them, and what it is
    to show. The shots already there are shown so the new one is written
    around them, and the instruction says not to write them again — the
    floor model copies what it is shown unless told what the list is for."""
    beat_id, anchor, side = _anchor_of(plan, place)
    beat = next(b for b in plan["beats"] if b["id"] == beat_id)
    seconds = director.allot_plan(plan)
    numbered = {s["id"]: at for at, s in enumerate(plan["shots"], 1)}
    siblings = [f"shot {numbered[s['id']]} — {s['action']}" for s in plan["shots"] if s["beat"] == beat_id]
    where = f"{side} shot {numbered[anchor]}" if anchor else f"{side} this beat"
    opens = (anchor == plan["shots"][0]["id"] and side == "before")
    return _message(
        _block("THE PIECE", [f"\"{plan['title']}\": {plan['brief']}"]),
        _camera_block(plan),
        _block("NAMES you may cite", _name_lines(plan, cast, ledger)),
        _block(f"THIS BEAT (about {seconds[beat_id]} seconds)", [beat["text"]]),
        _block("ITS SHOTS NOW (already written — do not write them again)", siblings),
        _block(f"THE NEW SHOT ({where})", [change]),
        "Write 1 shot: the new one only, showing what THE NEW SHOT says."
        + (" It opens the piece, so it is \"new\"." if opens else "") + " " + REPLY)


def _add_shot(plan, place, change, ask, log, cast, ledger):
    """A shot the person asked for, written by the shots call and put where
    the place says — at the end of the last beat when nowhere was said. ->
    the parts of `plan_turn`'s answer, `row` the new shot's id."""
    place = place or {"beat": plan["beats"][-1]["id"]}
    beat_id, _anchor, _side = _anchor_of(plan, place)
    shot = _call(ask, log, "shots", new_shot_message(plan, place, change, cast, ledger),
                 # Compared against every shot of the plan, its beat's too
                 # (`read_shots` spares the beat being written): a new shot
                 # that repeats one already there is the floor model copying.
                 lambda raw: _one(read_shots(raw, plan, None, ledger), "shot"),
                 label="turn.add")
    new = director.add_shot(plan, shot, **place)
    had = {s["id"] for s in plan["shots"]}
    row = next(s["id"] for s in new["shots"] if s["id"] not in had)
    return {"act": "add", "row": row, "plan": new, "render": None, "recast": None}


def _remove_row(plan, row_id):
    """A shot or a beat taken out, by `director`, with no call."""
    new = director.remove_beat(plan, row_id) if row_id.startswith("b") else director.remove_shot(plan, row_id)
    return {"act": "remove", "row": row_id, "plan": new, "render": None, "recast": None}


def _move_shot(plan, row_id, place):
    """A shot moved to its place, by `director`, with no call. A place that
    is the shot's own ("move the last shot to the end") moves nothing and
    says so."""
    if not place:
        raise director.PlanError(f"Say where {label_of(plan, row_id)} goes: before or after another "
                                 "shot, into a beat, first or last.")
    if row_id in place.values():
        raise director.PlanError(f"{label_of(plan, row_id)} is already there.")
    new = director.move_shot(plan, row_id, **place)
    return {"act": "move", "row": row_id, "plan": new, "render": None, "recast": None}


def _changed_picture(old, new, row_id, change):
    """A prep row whose picture was made before the change -> the edit-path
    render that changes it (`director.change_action`), under the row's mark
    in the changed plan. None when there is no picture to change: the row
    renders fresh from the plan when its turn comes."""
    if row_id not in director.handles_of(old):
        return None
    if not any(r["id"] == row_id for r in director.rows(new)):
        return None
    return {"row": row_id, "action": director.change_action(new, row_id, change),
            "mark": director.fingerprint(new, row_id)}


def replan(plan, change, ask, cast=(), ledger=(), seconds=None, log=None, text=None,
           steps=SMALL):
    """The plan rewritten from the beats down with `change` made -> the plan.

    The header is the basics call again with the change; then beats,
    entities and every beat's shots, as a first plan writes them — or, on
    the large profile, the structure call and the shot list, as a first plan
    on that profile writes them. What is kept is what was made: every
    person, place and thing the plan already holds keeps its id, its
    description and its sheet, and the entities call is told they exist and
    lists only what is new. A kept entity no new shot cites, and whose sheet
    was never made, goes. New beats and shots get new ids, so the clips and
    opening frames of the old ones have no row and their records go too
    (`director.prune`).
    """
    log = log if log is not None else []
    cast = _cast(cast)
    brief = " ".join(f"{plan['brief']} {change}".split())
    new = copy.deepcopy(plan)
    new.update(brief=brief, beats=[], shots=[])
    if steps_of(steps) == LARGE:
        new = _replan_large(new, change, ask, cast, ledger, seconds, log, text)
        return director.prune(director.validate(_cited_only(new)[0]))
    basics = _call(ask, log, "basics", header_message(plan, change, seconds),
                   lambda raw: director.read_basics(raw, seconds or plan["seconds"]),
                   label="replan.basics")
    new.update(basics)
    new = _cast_said(new, cast, text, change)
    # Everybody the plan holds reads to the new calls as already there.
    there = cast + [{"name": e["name"], "description": e["description"]}
                    for e in new["entities"] if "new" in (e.get("source") or {})]
    beats = _call(ask, log, "beats", beats_message(new, there), director.read_beats,
                  label="replan.beats")
    new = director.add_beats(new, beats)
    attached = {director.name_of(e["handle"]) for e in ledger or ()}
    entities = _call(ask, log, "entities", entities_message(new, there, ledger),
                     _reader_of_entities(brief, new, [e["name"] for e in new["entities"]],
                                         attached, [], []),
                     label="replan.entities")
    new = director.add_entities(new, entities)
    new = _write_shots(ask, log, new, cast, ledger)
    return director.prune(director.validate(_cited_only(new)[0]))


def _cast_said(new, cast, text, change):
    """A cast member the person's words cite, not yet in the plan, is in it
    as cast: "set it in winter, with @anna" casts Anna with no call."""
    have = {e["name"] for e in new["entities"]}
    for member in _said(cast, f"{text or ''} {change}"):
        if member["name"] not in have:
            new["entities"].append({"id": director._next_id(new, "e", new["entities"]),
                                    "name": member["name"], "kind": "person",
                                    "description": "", "source": {"cited": member["name"]}})
    return new


def _replan_large(new, change, ask, cast, ledger, seconds, log, text):
    """`replan` on the large profile: the structure again with the change,
    then the shot list. `new` is the plan with its brief extended and its
    beats and shots emptied."""
    plan = new
    new = _cast_said(new, cast, text, change)
    there = cast + [{"name": e["name"], "description": e["description"]}
                    for e in new["entities"] if "new" in (e.get("source") or {})]
    known = [e["name"] for e in new["entities"]]
    parts = _call(ask, log, "structure",
                  restructure_message(plan, change, there, ledger, seconds),
                  lambda raw: read_structure(raw, seconds or plan["seconds"], known,
                                             questions=False),
                  label="replan.structure")
    new.update(parts["basics"])
    if parts["assumptions"]:
        new["assumptions"] = parts["assumptions"]
    new = director.add_beats(new, parts["beats"])
    attached = {director.name_of(e["handle"]) for e in ledger or ()}
    new = director.add_entities(new, [e for e in parts["entities"] if e["name"] not in attached])
    return _write_shotlist(ask, log, new, cast, ledger, label="replan.shotlist")
