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
"""

import copy
import os
import re
import unicodedata

from . import director
from .families import refine


_PROMPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts", "director")

CALLS = ("brief", "basics", "beats", "entities", "shots")

_read = {}


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
        "look": {"type": "string"}},
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
                           "continues": {"type": "string", "enum": list(director.CONTINUES)}},
                          ("action", "continues"))},
        "required": ["shots"]},
}


# ---- what code counts for the model --------------------------------------------

_SECONDS_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*-?\s*(seconds?|secs?|s|minutes?|mins?)\b", re.IGNORECASE)


def asked_seconds(brief):
    """The length the brief asks for, in whole seconds, or None.

    The first length named wins: "a 40-second spot, each shot about 5 s" is a
    forty-second piece. Minutes are read as minutes. A number with no unit is
    not a length — "3 shots" is not three seconds.
    """
    match = _SECONDS_RE.search(brief or "")
    if not match:
        return None
    number = float(match.group(1))
    if match.group(2).lower().startswith("m"):
        number *= 60
    seconds = int(round(number))
    return seconds if director.MIN_SECONDS <= seconds <= director.MAX_SECONDS else None


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
    count = beats_for(plan["seconds"])
    many = "1 beat" if count == 1 else f"{count} beats"
    return _message(
        _block("THE BRIEF", [plan["brief"]]),
        _block("ASSUMED", [f"- {a}" for a in plan.get("assumptions") or ()]),
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
    count = shots_for(seconds)
    order = [b["id"] for b in plan["beats"]]
    before = [s for s in plan["shots"] if order.index(s["beat"]) < order.index(beat_id)]
    beat = next(b for b in plan["beats"] if b["id"] == beat_id)
    many = "1 shot" if count == 1 else f"1 to {count} shots"
    return _message(
        _block("THE PIECE", [f"\"{plan['title']}\": {plan['brief']}"]),
        _block("NAMES you may cite", _name_lines(plan, cast, ledger)),
        _block(f"THIS BEAT (about {seconds} seconds)", [beat["text"]]),
        f"Write {many} that show this beat and nothing else."
        + (" It opens the piece, so its first shot is \"new\"." if not before else "")
        + " " + REPLY)


def beat_seconds(plan):
    """`{beat id: seconds}` as the beats stand, before any shots exist: the
    share each beat will get, which is what the shots call is told."""
    beats = plan["beats"]
    shares = director.allot(int(plan["seconds"]),
                            [director.WEIGHTS.get(b.get("weight"), 2) for b in beats])
    return {b["id"]: s for b, s in zip(beats, shares)}


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

    if isinstance(items, list):
        items = [dict(i, action=tidy(i["action"]))
                 if isinstance(i, dict) and isinstance(i.get("action"), str) else i
                 for i in items]
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


def _write_shots(ask, log, plan, cast, ledger, beats=None):
    """One shots call per beat, in order -> the plan with their shots."""
    for beat in list(beats if beats is not None else plan["beats"]):
        shots = _call(
            ask, log, "shots", shots_message(plan, beat["id"], cast, ledger),
            lambda raw, at=beat["id"]: read_shots(raw, plan, at, ledger),
            label=f"shots.{beat['id']}")
        plan = director.set_shots(plan, beat["id"], shots)
    return plan


def plan_piece(brief, rail, ask, cast=(), ledger=(), keyframes=None,
               shot_limit=director.SHOT_LIMIT, questions=True):
    """A brief -> `{"plan", "questions", "log", "relisted"}`.

    `ask(system, message, schema, label) -> reply text` is the one model call.
    `cast` is `[{name, description}]`, the people the brief cites; `ledger`
    is `[{handle, kind, text}]`, the pictures it cites. With `questions` on,
    a brief call that asks something stops planning there and `plan` is
    None: the room shows the questions and the person's answer is the next
    brief. `relisted` names cast members the entities call listed anyway and
    code dropped — not wrong about the piece, but measured, since a model
    that does it is not reading the cast block. `invented` names entities
    code dropped because nothing in the brief or the beats speaks of them.
    `warnings` are the doubts a re-ask did not clear (`Doubt`), by call.

    Raises `PlanningFailed` when a call fails its re-ask.
    """
    log, plan = [], None
    cast = _cast(cast)
    cast_names = [m["name"] for m in cast]
    relisted, invented = [], []

    try:
        assumptions = []
        if questions:
            asked, assumptions = _call(ask, log, "brief", brief_message(brief, cast, ledger),
                                       read_brief)
            if asked:
                return {"plan": None, "questions": asked, "assumptions": assumptions,
                        "log": log, "relisted": relisted, "invented": invented}

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
        plan = director.validate(_write_shots(ask, log, plan, cast, ledger))
    except director.PlanError as problem:
        raise PlanningFailed(str(problem), plan, log) from None
    return {"plan": plan, "questions": [], "assumptions": plan.get("assumptions") or [],
            "log": log, "relisted": relisted, "invented": invented,
            "warnings": _warnings(log)}


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

TURN_ACTS = ("edit", "replan", "say")

SCHEMAS["turn"] = {"type": "object", "properties": {
    "act": {"type": "string", "enum": list(TURN_ACTS)},
    "row": {"type": "string"}, "change": {"type": "string"}, "say": {"type": "string"}},
    "required": ["act", "row", "change", "say"]}

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
                 "the look", "the length"}
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
    look = plan.get("look") or "none"
    out = [f"{PIECE} — \"{plan['title']}\", {plan['seconds']} seconds, look: {look}"]
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
    """The turn call -> `{act, row, change, say}`. A change left empty is the
    person's own words, which say it as well as any rewording would."""
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
        raise director.PlanError(f'"act" must be edit, replan or say; it was {director._shown(raw.get("act"))}.')
    change, say = _sentence(raw.get("change")), _sentence(raw.get("say"))
    if act == "say":
        if not (say or change):
            raise director.PlanError('a "say" reply needs "say": the sentence to answer with.')
        return {"act": act, "row": None, "change": "", "say": say or change}
    row = row_of(plan, raw.get("row")) if act == "edit" else None
    entity = next((e for e in plan["entities"] if e["id"] == row), None)
    if entity and "cited" in (entity.get("source") or {}) and not _cites_cast(text, entity):
        # Somebody the person cast is used as they are, so their row has
        # nothing to change; on the floor model it is the row picked for "he"
        # in a message about a shot.
        raise director.PlanError(
            f"@{entity['name']} is from the cast and is used as they are, so their row "
            f"cannot change. Pick the row the message is about.")
    return {"act": act, "row": row, "change": change or _sentence(text), "say": say}


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


def named_rows(plan, text):
    """The beats and shots the person's words name by number or position ->
    their ids, in order, each once. "The last beat", "shot 3", "the 2nd
    shot"; one past the end names nothing."""
    out = []
    for match in _NAMED_ROW_RE.finditer(text or ""):
        word, kind = (match.group(1), match.group(2)) if match.group(2) else (match.group(4), match.group(3))
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


def overrule(turn, plan, text):
    """The turn call's answer, with what the words say plainly put first ->
    `(turn, note)`; `note` says what code changed, or is None.

    A title or a length the person names, with no beat or shot named beside
    it, is the piece's header ("make shot 2 five seconds" is not a length
    for the piece). A beat or shot named alone is the row an edit is about.
    A question keeps its answer: "is 20 seconds too long?" asks nothing."""
    named = named_rows(plan, text)
    asking = text.rstrip().endswith("?")
    header = asked_title(text) or (not named and asked_seconds(text) not in (None, plan["seconds"]))
    if header and not asking and turn["act"] != "replan" and turn["row"] != director.HEADER:
        was = turn["row"] or turn["act"]
        return {**turn, "act": "edit", "row": director.HEADER,
                "change": turn["change"] or _sentence(text)}, f"{was} -> header"
    if turn["act"] == "edit" and len(named) == 1 and turn["row"] != named[0]:
        return {**turn, "row": named[0]}, f"{turn['row']} -> {named[0]}"
    return turn, None


def _now_line(plan):
    return f"\"{plan['title']}\", {plan['seconds']} seconds, look: {plan.get('look') or 'none'}"


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
        "Give the piece its title, length and look. " + _keep("them") + f" {length} " + REPLY)


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
               [shot["action"]]),
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


def plan_turn(plan, text, ask, cast=(), ledger=()):
    """Something said about an open plan -> `{"plan", "act", "row", "say",
    "render", "recast", "log", "warnings"}`.

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
                if row is None or not isinstance(raw, dict) or raw.get("act") != "edit":
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
            out["plan"] = replan(plan, turn["change"], ask, cast, ledger, seconds, log, text)
        else:
            out.update(_edit_row(plan, turn["row"], turn["change"], text, ask, log,
                                 cast, ledger, seconds))
    except director.PlanError as problem:
        if len(log) == 1 and log[0]["call"] == "turn":
            # The turn call itself failed twice: what reaches the person is
            # what to do, not the sentence the model was re-asked with.
            problem = ("Could not tell what that changes in the plan. Name the row as "
                       "the card does (“shot 2”, “beat 1”, “@keeper”), or change it on the card.")
        raise PlanningFailed(str(problem), plan, log) from None
    return {**out, "warnings": _warnings(log)}


def _edit_row(plan, row_id, change, text, ask, log, cast, ledger, seconds):
    """One row, changed by its own call. -> the parts of `plan_turn`'s answer
    that say what happened."""
    out = {"act": "edit", "row": row_id, "render": None, "recast": None}
    if row_id == director.HEADER:
        title = asked_title(text)

        def read(raw):
            basics = director.read_basics(raw, seconds or plan["seconds"])
            if title:
                basics["title"] = title
            return _changed(basics, {k: plan.get(k) for k in basics}, "title, length and look")
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
                       plan=replan(plan, change, ask, cast, ledger, basics["seconds"], log, text))
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
                                           {k: shot[k] for k in ("action", "continues")}, "shot"),
                      label="turn.shot")
    new = director.edit(plan, row_id, rewritten)
    out["plan"] = new
    frame = next((r["id"] for r in director.rows(new)
                  if r["kind"] == "keyframe" and r["shot"] == row_id), None)
    out["render"] = _changed_picture(plan, new, frame, change) if frame else None
    return out


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


def replan(plan, change, ask, cast=(), ledger=(), seconds=None, log=None, text=None):
    """The plan rewritten from the beats down with `change` made -> the plan.

    The header is the basics call again with the change; then beats,
    entities and every beat's shots, as a first plan writes them. What is
    kept is what was made: every person, place and thing the plan already
    holds keeps its id, its description and its sheet, and the entities call
    is told they exist and lists only what is new. A kept entity no new shot
    cites, and whose sheet was never made, goes. New beats and shots get
    new ids, so the clips and opening frames of the old ones have no row
    and their records go too (`director.prune`).
    """
    log = log if log is not None else []
    cast = _cast(cast)
    brief = " ".join(f"{plan['brief']} {change}".split())
    basics = _call(ask, log, "basics", header_message(plan, change, seconds),
                   lambda raw: director.read_basics(raw, seconds or plan["seconds"]),
                   label="replan.basics")
    new = copy.deepcopy(plan)
    new.update(basics, brief=brief, beats=[], shots=[])
    have = {e["name"] for e in new["entities"]}
    for member in _said(cast, f"{text or ''} {change}"):
        if member["name"] not in have:
            new["entities"].append({"id": director._next_id(new, "e", new["entities"]),
                                    "name": member["name"], "kind": "person",
                                    "description": "", "source": {"cited": member["name"]}})
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
    cited = {w.lower() for s in new["shots"] for w in director.CITE_RE.findall(s["action"])}
    made = director.handles_of(new)
    new["entities"] = [e for e in new["entities"]
                       if e["name"] in cited or e["id"] in made
                       or "cited" in (e.get("source") or {})]
    return director.prune(director.validate(new))
