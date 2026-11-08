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
entities, and the shots, one call per beat. Each answers one small object
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
    cast = [{"name": director.name_of(m["name"]), "description": m.get("description") or ""}
            for m in cast or ()]
    cast_names = [m["name"] for m in cast]
    relisted, invented = [], []

    def failed(problem):
        return PlanningFailed(str(problem), plan, log)

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

        def read_entities(raw):
            items = raw.get("entities") if isinstance(raw, dict) else raw
            listed = {director.name_of((i or {}).get("name")) for i in items or ()
                      if isinstance(i, dict)}
            entities = director.read_entities(raw, cast_names)
            relisted[:] = sorted(n for n in listed if n in cast_names)
            # An attached picture listed as somebody: `@pic-1` read as a
            # person called Pic-1. It is already a picture; drop it. And an
            # entity neither the brief nor any beat speaks of has no shot to
            # be in — on the floor model, it is the prompt file's worked
            # example copied into a piece it has nothing to do with.
            told = " ".join([brief] + [b["text"] for b in plan["beats"]])
            entities = [e for e in entities if e["name"] not in attached]
            invented[:] = sorted(e["name"] for e in entities if not mentioned(e, told))
            return [e for e in entities if e["name"] not in invented]

        attached = {director.name_of(e["handle"]) for e in ledger or ()}
        entities = _call(ask, log, "entities", entities_message(plan, cast, ledger),
                         read_entities)
        plan = director.add_entities(plan, entities)

        for beat in list(plan["beats"]):
            shots = _call(
                ask, log, "shots", shots_message(plan, beat["id"], cast, ledger),
                lambda raw: read_shots(raw, plan, beat["id"], ledger),
                label=f"shots.{beat['id']}")
            plan = director.set_shots(plan, beat["id"], shots)
        plan = director.validate(plan)
    except director.PlanError as problem:
        raise failed(problem) from None
    return {"plan": plan, "questions": [], "assumptions": plan.get("assumptions") or [],
            "log": log, "relisted": relisted, "invented": invented,
            "warnings": [f"{e['label']}: {e['warning']}" for e in log if e.get("warning")]}
