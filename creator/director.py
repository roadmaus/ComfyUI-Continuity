"""Director's plan: the document a piece is planned in, and everything about it
that is arithmetic or bookkeeping.

The chat makes one thing a turn. Director makes a piece — the cast, the
places, the props, then a shot list longer than one clip — and it does that by
asking the model many small questions and keeping the answers here, in a plan
(`specs/continuity-agent-spec.md`). This module is the half of that which is
not a model: what a plan may hold, how many seconds each shot gets, where a
long shot is cut, what must render before what, what has gone stale, and what
ordinary chat action each row of the plan becomes. Pure: no ComfyUI, no disk,
no model, the same bargain `chat.py` keeps, so every rule here is tested as
data.

**The model writes words; code writes numbers.** A beat arrives with a rough
weight (`short`, `medium`, `long`), never a duration, and a shot arrives with
an action and how it joins the one before, never a length. `allot` turns
weights into whole seconds that add up to the target exactly, and `clips`
cuts any shot longer than the limit into continuation parts. A small model
asked for twelve-second shots in a forty-second film writes four of them; a
small model asked which beat is the long one is usually right.

**What the person wrote and what has been rendered are kept apart.** `beats`,
`entities` and `shots` are authored rows: the model fills them and the person
edits them. Renderable rows — a sheet per new entity, a keyframe per opening,
a clip per part — are *derived* from those by `rows`, every time, and what has
been rendered of them sits in `renders`, keyed by row id. That is what lets a
change of rail re-split every shot without losing anything: the clips are
recomputed, and a render whose row still exists with the same fingerprint is
still that row's.

**Stale is a fingerprint, not a flag.** A row's fingerprint hashes what it
renders from — its prompt, its family, its length, and what it cites, by the
handle of the picture it cites once there is one. A redone sheet lands with a
new handle, so every keyframe citing it gets a new fingerprint, so the
keyframe's stored render no longer matches: stale, and so is the clip that
opens on it. Nobody walks the graph marking things; the graph is the hash.

**A row becomes an action the room already renders.** `action_for` writes the
chat's own nine-field action — the same dict `chat.validate` returns — so a run
is a sequence of ordinary chat renders nobody had to type, and after the run
"make shot 3 darker" is an ordinary turn about an ordinary clip.

**Ids, not positions.** Every authored row has an id minted once (`b3`, `e2`,
`s5`) and never reused, so an edit to one row never renumbers another, and a
derived row's id is built from its authored row's (`kf.s5`, `s5.2`).
"""

import copy
import hashlib
import json
import math
import re
import unicodedata

from .chat import ACT_RENDER, KIND_STILL, KIND_VIDEO, ROLE_START


VERSION = 1


class PlanError(ValueError):
    """A plan, or a piece of one, this module will not keep — as a sentence.

    Same deal as `chat.ActionError`: the sentence names the row and the field
    and what arrived, because it is quoted back to the model on the one re-ask
    and shown to the person if that fails too.
    """


# ---- vocabulary --------------------------------------------------------------

# A beat's rough share of the piece. Three words because three is what a small
# model can rank reliably; the numbers are the ratio between them.
WEIGHTS = {"short": 1, "medium": 2, "long": 3}

KINDS = ("person", "place", "thing")

# How a shot joins the one before it. `cut` is the same moment from a new
# angle, `pin` the same camera carrying straight on, `new` a real cut — a time
# skip or a new scene. The first shot of a piece is always `new`.
CUT, PIN, NEW = "cut", "pin", "new"
CONTINUES = (CUT, PIN, NEW)

# What the shot prompt says on top of its own action for the two continuous
# joins. Fixed wording, appended by code, never written by the model: the
# point is that it reads identically on every shot.
CONTINUITY = {
    CUT: "Same moment as the previous shot, seen from a new camera angle.",
    PIN: "The camera holds its position and the action carries straight on "
         "from the previous shot.",
}

# The reference a place or a thing is cited as on a shot — the compiler's own
# scope names (`compile.IMAGE_TAKES`). A person is cited by name instead, as a
# member of the cast.
SCOPES = {"place": "scene", "thing": "object"}

# What a sheet is a picture of, per kind. The entity's description goes in the
# braces; the look goes after, as it does on every prompt.
SHEETS = {
    "person": ("Character reference of {description}. Full body, facing the "
               "camera, neutral expression, standing against a plain neutral "
               "grey background in even, soft studio light."),
    "place": ("Empty establishing view of {description}. Wide shot, no people, "
              "nothing happening, the whole place readable."),
    "thing": ("Reference photograph of {description}, alone and centred on a "
              "plain neutral background in even, soft studio light."),
}

# Row states. A prep row is approved by the person; a run row is approved by
# rendering — nobody looks at it before the next step needs it.
PLANNED, RENDERING, PENDING, APPROVED, STALE, FAILED = (
    "planned", "rendering", "pending", "approved", "stale", "failed")
STATES = (PLANNED, RENDERING, PENDING, APPROVED, STALE, FAILED)

PREP, RUN = "prep", "run"

# Planning defaults. The limit is a planning choice, under what the families
# declare (H3 and LTX both accept 60 s): fifteen seconds is about where one
# generation stops holding a single idea together.
SHOT_LIMIT = 15
MIN_SECONDS = 1
DEFAULT_SECONDS = 30
MAX_SECONDS = 600

# One beat is a piece that is one moment: "a single 6 s shot" planned as a
# piece is still one beat, and forcing a second would cut it in two.
MIN_BEATS, MAX_BEATS = 1, 8
MAX_TEXT = 600

# A name the cast can hold: `subjects.HANDLE_RE`, spelled here so this module
# loads without the family package. `tests/test_director.py` holds the two
# together.
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")
CITE_RE = re.compile(r"@([A-Za-z][A-Za-z0-9_]*)\b(?!-)")


# ---- small readers -----------------------------------------------------------

def _shown(value):
    try:
        text = json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        text = repr(value)
    return text if len(text) <= 60 else text[:57] + "…"


def _text(value, label, required=True):
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise PlanError(f"{label} must be a sentence; it was empty.")
        return ""
    if not isinstance(value, str):
        raise PlanError(f"{label} must be a sentence; it was {_shown(value)}.")
    return " ".join(value.split())[:MAX_TEXT]


def _whole(value, label, low, high):
    """A whole number in [low, high]. A numeric string counts; `true` does not."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise PlanError(f"{label} must be a number; it was {_shown(value)}.")
    try:
        number = float(value)
    except ValueError:
        raise PlanError(f"{label} must be a number; it was {_shown(value)}.") from None
    if not math.isfinite(number):
        raise PlanError(f"{label} must be a number; it was {_shown(value)}.")
    number = int(round(number))
    if not low <= number <= high:
        raise PlanError(f"{label} must be between {low} and {high}; it was {number}.")
    return number


def name_of(text):
    """What a model or a person called an entity -> a name the cast can hold.

    `"Old keeper"` is `old_keeper`. Read rather than refused: the meaning is
    not in doubt, and the name is only ever a citation in this pack's own
    prompts. What cannot become a name at all is refused by the caller.
    """
    # Accents fold rather than vanish: a café is `cafe`, not `caf`.
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii")
    name = re.sub(r"[^A-Za-z0-9_]+", "_", text.strip().lstrip("@")).strip("_")
    name = name.lower()[:32]
    return name if NAME_RE.match(name) else ""


def mint(rows, prefix):
    """The next unused id for `prefix`: one past the highest ever seen.

    One past the highest *present*, which after a delete can reuse a number —
    so the plan keeps a counter as well (`ids`), and this is only the
    fallback for a plan that has none.
    """
    used = [int(m.group(1)) for r in rows or []
            for m in [re.match(rf"^{prefix}(\d+)$", str(r.get("id") or ""))] if m]
    return f"{prefix}{max(used, default=0) + 1}"


def _next_id(plan, prefix, rows):
    counters = plan.setdefault("ids", {})
    seen = int(mint(rows, prefix)[len(prefix):])
    number = max(seen, int(counters.get(prefix) or 0) + 1)
    counters[prefix] = number
    return f"{prefix}{number}"


# ---- what the model's calls return -------------------------------------------

def read_basics(raw, seconds=None):
    """The basics call -> `{title, seconds, look}`.

    `seconds` is what the person asked for, when the room could read a number
    in the brief: theirs wins over the model's, since it is a decision and not
    a guess.
    """
    if not isinstance(raw, dict):
        raise PlanError('the basics must be a JSON object with "title", "seconds" and "look".')
    title = _text(raw.get("title"), '"title"')[:80]
    asked = seconds if seconds is not None else raw.get("seconds")
    total = DEFAULT_SECONDS if asked in (None, "") else _whole(asked, '"seconds"', 1, MAX_SECONDS)
    look = _text(raw.get("look"), '"look"', required=False)
    return {"title": title, "seconds": total, "look": look}


def read_beats(raw):
    """The beats call -> `[{text, weight}]`, 1 to 8 of them, in order."""
    items = raw.get("beats") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        raise PlanError('"beats" must be a list of {"text", "weight"} objects.')
    if not MIN_BEATS <= len(items) <= MAX_BEATS:
        raise PlanError(f'"beats" must hold {MIN_BEATS} to {MAX_BEATS} beats; it held {len(items)}.')
    return [_read_beat(item, f"beat {at}") for at, item in enumerate(items, 1)]


def _read_beat(item, label):
    if isinstance(item, str):
        item = {"text": item}
    if not isinstance(item, dict):
        raise PlanError(f"{label} must be an object; it was {_shown(item)}.")
    weight = str(item.get("weight") or "medium").strip().lower()
    if weight not in WEIGHTS:
        raise PlanError(f'{label}\'s "weight" must be short, medium or long; '
                        f"it was {_shown(item.get('weight'))}.")
    return {"text": _text(item.get("text"), f'{label}\'s "text"'), "weight": weight}


def read_entities(raw, cast=()):
    """The entities call -> `[{name, kind, description}]`.

    Somebody the person cited is already cast and is not the model's to list
    again; a model that lists them anyway is not wrong about the piece, so the
    row is dropped rather than refused. Two rows with one name are one.
    """
    items = raw.get("entities") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        raise PlanError('"entities" must be a list of {"name", "kind", "description"} objects.')
    cast = {str(n).lower() for n in cast or ()}
    out, seen = [], set()
    for at, item in enumerate(items, 1):
        if not isinstance(item, dict):
            raise PlanError(f"entity {at} must be an object; it was {_shown(item)}.")
        name = name_of(item.get("name"))
        if not name:
            raise PlanError(f'entity {at}\'s "name" must be a word or two, like "keeper"; '
                            f"it was {_shown(item.get('name'))}.")
        kind = str(item.get("kind") or "").strip().lower()
        if kind not in KINDS:
            raise PlanError(f'entity @{name}\'s "kind" must be person, place or thing; '
                            f"it was {_shown(item.get('kind'))}.")
        if name in cast or name in seen:
            continue
        seen.add(name)
        out.append({"name": name, "kind": kind,
                    "description": _text(item.get("description"), f'entity @{name}\'s "description"')})
    return out


def read_shots(raw, names):
    """One beat's shots call -> `[{action, continues}]`.

    `names` is every name a shot may cite: the cast and the entities. A
    citation that resolves to nobody is refused with the list, the same as
    the chat refuses one.
    """
    items = raw.get("shots") if isinstance(raw, dict) else raw
    if not isinstance(items, list) or not items:
        raise PlanError('"shots" must be a list of at least one {"action", "continues"} object.')
    out = []
    for at, item in enumerate(items, 1):
        if isinstance(item, str):
            item = {"action": item}
        if not isinstance(item, dict):
            raise PlanError(f"shot {at} must be an object; it was {_shown(item)}.")
        action = _text(item.get("action"), f'shot {at}\'s "action"')
        continues = str(item.get("continues") or NEW).strip().lower()
        if continues not in CONTINUES:
            raise PlanError(f'shot {at}\'s "continues" must be cut, pin or new; '
                            f"it was {_shown(item.get('continues'))}.")
        _check_cites(action, names, f"shot {at}")
        out.append({"action": action, "continues": continues})
    return out


def _check_cites(text, names, label):
    known = {str(n).lower() for n in names}
    for word in CITE_RE.findall(text or ""):
        if word.lower() not in known:
            where = ", ".join("@" + n for n in sorted(known)) or "nobody"
            raise PlanError(f"{label} cites @{word}, who is not in the plan. "
                            f"The names you may cite are: {where}.")


# ---- the document ------------------------------------------------------------

def new_plan(brief, basics, rail, cast=(), assumptions=(), keyframes=None,
             shot_limit=SHOT_LIMIT):
    """A plan with its header and nothing else, ready for beats.

    `cast` is the people the person cited, by name: each becomes an entity
    whose source is the citation, approved from the start, so the entity call
    is told they exist and the shots may cite them.

    `keyframes` is the storyboard toggle. Unsaid, it follows the rail's video
    family: one that is sent references (`rail["references"]`) opens each shot
    from its cast and references directly, and an opening still drawn first
    by the still family would only pin the shot to a worse picture of the
    same people — so the storyboard starts off. A family that takes no
    references starts with it on.
    """
    if keyframes is None:
        keyframes = not (rail or {}).get("references")
    plan = {
        "version": VERSION,
        "brief": _text(brief, "the brief"),
        "assumptions": [_text(a, "an assumption") for a in assumptions or () if str(a or "").strip()],
        **basics,
        "rail": follow_rail({}, rail)[0]["rail"],
        "shot_limit": _whole(shot_limit, "the shot limit", 1, MAX_SECONDS),
        "keyframes": bool(keyframes),
        "beats": [], "entities": [], "shots": [],
        "renders": {}, "ids": {},
    }
    for member in cast or ():
        name = name_of(member)
        if not name:
            raise PlanError(f"@{member} is not a name the cast can hold.")
        plan["entities"].append({"id": _next_id(plan, "e", plan["entities"]), "name": name,
                                 "kind": "person", "description": "",
                                 "source": {"cited": name}})
    return plan


def add_beats(plan, beats):
    plan = copy.deepcopy(plan)
    for beat in beats:
        plan["beats"].append({"id": _next_id(plan, "b", plan["beats"]), **beat})
    return plan


def add_entities(plan, entities):
    plan = copy.deepcopy(plan)
    have = {e["name"] for e in plan["entities"]}
    for entity in entities:
        if entity["name"] in have:
            continue
        have.add(entity["name"])
        plan["entities"].append({"id": _next_id(plan, "e", plan["entities"]),
                                 **entity, "source": {"new": True}})
    return plan


def set_shots(plan, beat_id, shots):
    """One beat's shots, replacing whatever that beat had, in the beat's place.

    The first shot of the whole piece cannot continue from anything, so it is
    `new` whatever the model wrote.
    """
    plan = copy.deepcopy(plan)
    if not any(b["id"] == beat_id for b in plan["beats"]):
        raise PlanError(f"there is no beat {beat_id} in the plan.")
    order = [b["id"] for b in plan["beats"]]
    kept = [s for s in plan["shots"] if s["beat"] != beat_id]
    made = [{"id": _next_id(plan, "s", plan["shots"] + kept), "beat": beat_id, **s} for s in shots]
    # Keep ids monotonic across both lists: `_next_id` saw the old shots.
    merged = kept + made
    merged.sort(key=lambda s: order.index(s["beat"]) if s["beat"] in order else len(order))
    if merged:
        merged[0] = {**merged[0], "continues": NEW}
    plan["shots"] = merged
    return plan


def names(plan):
    """Every name a shot may cite: the entities, cited and new alike."""
    return [e["name"] for e in plan.get("entities") or []]


def validate(plan):
    """A whole plan, as saved or as edited on the card -> the plan, or a
    `PlanError`. Checks what code relies on: ids unique, every shot under a
    beat that exists, every beat with a shot, every citation resolving, and
    seconds that can be shared out at all."""
    if not isinstance(plan, dict) or plan.get("version") != VERSION:
        raise PlanError("this is not a Director plan this version can read.")
    seen = set()
    for key in ("beats", "entities", "shots"):
        for row in plan.get(key) or []:
            if row.get("id") in seen:
                raise PlanError(f"{row.get('id')} is used by two rows.")
            seen.add(row.get("id"))
    beats = {b["id"] for b in plan["beats"]}
    for shot in plan["shots"]:
        if shot.get("beat") not in beats:
            raise PlanError(f"shot {shot['id']} belongs to beat {shot.get('beat')}, "
                            f"which is not in the plan.")
        if shot.get("continues") not in CONTINUES:
            raise PlanError(f"shot {shot['id']}'s join must be cut, pin or new.")
        _check_cites(shot.get("action"), names(plan), f"shot {shot['id']}")
    empty = [b["id"] for b in plan["beats"] if not any(s["beat"] == b["id"] for s in plan["shots"])]
    if empty:
        raise PlanError(f"beat {empty[0]} has no shots.")
    allot_plan(plan)
    return plan


# ---- seconds -----------------------------------------------------------------

def allot(total, weights, floors=None):
    """Share `total` whole seconds out by `weights` -> a list that sums to it.

    Largest remainder: each share is its exact proportion rounded down, then
    the seconds left over go to the shares that lost the most to the rounding,
    first in order on a tie. `floors` is the least each share may have; a
    share below its floor is lifted to it and the seconds come off the shares
    furthest above theirs. A total that cannot cover the floors is refused —
    that is a plan with more shots than its length can hold.
    """
    count = len(weights)
    if not count:
        return []
    floors = list(floors) if floors is not None else [MIN_SECONDS] * count
    if total < sum(floors):
        raise PlanError(f"{total} seconds cannot hold {count} parts of at least "
                        f"{max(floors)} seconds each; make it longer or use fewer shots.")
    weight_sum = float(sum(weights)) or float(count)
    exact = [total * (w or 0) / weight_sum if sum(weights) else total / count for w in weights]
    out = [max(f, int(math.floor(x))) for x, f in zip(exact, floors)]
    while sum(out) < total:
        at = max(range(count), key=lambda i: (exact[i] - out[i], -i))
        out[at] += 1
    while sum(out) > total:
        at = max((i for i in range(count) if out[i] > floors[i]),
                 key=lambda i: (out[i] - exact[i], out[i], -i))
        out[at] -= 1
    return out


def limit_of(plan):
    """The longest one clip may run: the plan's limit, under the rail's video
    family's own ceiling."""
    rail = plan.get("rail") or {}
    ceiling = rail.get("max_seconds")
    limit = int(plan.get("shot_limit") or SHOT_LIMIT)
    return max(1, min(limit, int(ceiling))) if ceiling else limit


def floor_of(plan):
    """The shortest one clip may run: the rail's video family's floor."""
    return max(MIN_SECONDS, int(math.ceil((plan.get("rail") or {}).get("min_seconds") or MIN_SECONDS)))


def allot_plan(plan):
    """`{beat id: seconds, shot id: seconds}`, adding up to the plan's length.

    Beats share the piece by weight, and each beat is floored at enough for
    its shots; shots share their beat evenly. A shot over the limit is still
    one row here — `clips` cuts it.
    """
    floor = floor_of(plan)
    beats = plan.get("beats") or []
    counts = [sum(1 for s in plan["shots"] if s["beat"] == b["id"]) for b in beats]
    beat_seconds = allot(int(plan["seconds"]), [WEIGHTS.get(b.get("weight"), 2) for b in beats],
                         [max(1, c) * floor for c in counts])
    out = {}
    for beat, seconds, count in zip(beats, beat_seconds, counts):
        out[beat["id"]] = seconds
        shots = [s for s in plan["shots"] if s["beat"] == beat["id"]]
        for shot, share in zip(shots, allot(seconds, [1] * count, [floor] * count) if count else []):
            out[shot["id"]] = share
    return out


def clips(plan):
    """The clips the run renders, in strip order -> `[{id, shot, part, parts,
    seconds, continues}]`.

    A shot over the limit becomes as many parts as it needs, as even as whole
    seconds allow, and every part after the first is a `pin` of the one
    before: the camera carries on, the cut is not a cut. A shot that fits is
    one clip under the shot's own id, so the common case reads plainly.
    """
    seconds = allot_plan(plan)
    limit, floor = limit_of(plan), floor_of(plan)
    out = []
    for shot in plan["shots"]:
        total = seconds[shot["id"]]
        parts = max(1, math.ceil(total / limit))
        shares = allot(total, [1] * parts, [floor] * parts) if parts > 1 else [total]
        for at, share in enumerate(shares, 1):
            out.append({"id": shot["id"] if parts == 1 else f"{shot['id']}.{at}",
                        "shot": shot["id"], "part": at, "parts": parts, "seconds": share,
                        "continues": shot["continues"] if at == 1 else PIN})
    if out:
        out[0]["continues"] = NEW
    return out


# ---- the rail ----------------------------------------------------------------

RAIL_KEYS = ("still", "edit", "video", "aspect", "min_seconds", "max_seconds", "references")


def follow_rail(plan, rail):
    """The room's rail now -> `(plan, what moved)`.

    The rail is a snapshot, not a choice: rows not yet rendered follow what
    the room has selected, and a new video family can move every cut point.
    What moved is said as the clips that came or went, so the card can say
    so; renders keep their rows by id, and a clip whose length changed is
    stale through its fingerprint.
    """
    rail = rail or {}
    snapshot = {
        "still": rail.get("still") or rail.get("still_family"),
        "edit": rail.get("edit") or rail.get("edit_family"),
        "video": rail.get("video") or rail.get("video_family"),
        "aspect": rail.get("aspect"),
        "min_seconds": rail.get("min_seconds"),
        "max_seconds": rail.get("max_seconds"),
        "references": bool(rail.get("references")),
    }
    if not plan.get("version"):
        return {"rail": snapshot}, []
    before = [c["id"] for c in clips(plan)] if plan.get("shots") else []
    plan = copy.deepcopy(plan)
    plan["rail"] = snapshot
    after = [c["id"] for c in clips(plan)] if plan.get("shots") else []
    moved = [f"-{c}" for c in before if c not in after] + [f"+{c}" for c in after if c not in before]
    return plan, moved


# ---- rows ----------------------------------------------------------------------

def _entity(plan, name):
    return next((e for e in plan["entities"] if e["name"] == str(name).lower()), None)


def _cited_entities(plan, text):
    out = []
    for word in CITE_RE.findall(text or ""):
        entity = _entity(plan, word)
        if entity and entity not in out:
            out.append(entity)
    return out


def _renders(entity):
    return "new" in (entity.get("source") or {})


def rows(plan):
    """Every renderable row, in the order it may render -> `[{id, kind,
    phase, deps, ...}]`.

    Sheets first, one per entity the plan made up (a cited person needs
    none). Then, while the plan's storyboard toggle is on, each clip's
    keyframe where its clip opens on one — the first part of a `cut` or a
    `new` shot — as prep, for the person to approve. Off, there are none:
    the clip opens from what it cites, the cast by name and the places and
    things by their sheets. Then the clips, each depending on its keyframe
    if it has one, the sheets it cites, and the clip in front of it.

    The list is already in dependency order: everything a row depends on
    comes earlier in it, so the run's order is this order.
    """
    out = []
    for entity in plan["entities"]:
        if _renders(entity):
            out.append({"id": entity["id"], "kind": "sheet", "phase": PREP,
                        "entity": entity["id"], "deps": []})
    shots = {s["id"]: s for s in plan["shots"]}
    storyboard = plan.get("keyframes", True)
    previous = None
    clip_rows = []
    for clip in clips(plan):
        shot = shots[clip["shot"]]
        sheets = [e["id"] for e in _cited_entities(plan, shot["action"]) if _renders(e)]
        deps = list(sheets)
        if storyboard and clip["part"] == 1 and clip["continues"] in (CUT, NEW):
            key = f"kf.{clip['id']}"
            out.append({"id": key, "kind": "keyframe", "phase": PREP,
                        "clip": clip["id"], "shot": shot["id"], "deps": list(sheets)})
            deps.append(key)
        if previous:
            deps.append(previous)
        clip_rows.append({"id": clip["id"], "kind": "clip", "phase": RUN, "clip": clip["id"],
                          "shot": shot["id"], "seconds": clip["seconds"],
                          "continues": clip["continues"], "deps": deps})
        previous = clip["id"]
    return out + clip_rows


def _row(plan, row_id, every=None):
    for row in every if every is not None else rows(plan):
        if row["id"] == row_id:
            return row
    raise PlanError(f"there is no row {row_id} in the plan.")


# ---- prompts -------------------------------------------------------------------

def _with_look(prompt, plan):
    look = (plan.get("look") or "").strip()
    return f"{prompt}\n\nLook: {look.rstrip('.')}." if look else prompt


def _resolve(plan, text, handles):
    """A shot's prose -> `(prompt, from)`: cast names stay citations, cited
    people read as whom they cite, and places and things become the handle of
    their approved sheet with the scope that says what of it to take."""
    cited = []

    def swap(match):
        entity = _entity(plan, match.group(1))
        if entity is None:
            return match.group(0)
        source = entity.get("source") or {}
        if "cited" in source:
            return "@" + source["cited"]
        if entity["kind"] == "person":
            return "@" + entity["name"]
        handle = handles.get(entity["id"])
        if not handle:
            raise PlanError(f"@{entity['name']} has no sheet yet.")
        item = f"{handle}:{SCOPES[entity['kind']]}"
        if item not in cited:
            cited.append(item)
        return "@" + handle

    return CITE_RE.sub(swap, text), cited


def handles_of(plan):
    """`{row id: handle}` for every row with a render landed on it."""
    return {rid: r["handle"] for rid, r in (plan.get("renders") or {}).items()
            if isinstance(r, dict) and r.get("handle")}


def cast_of(plan):
    """The names an action may cite as cast: the cited people, and every new
    person — whose approved sheet the room adds to the chat's cast under the
    entity's name."""
    out = []
    for entity in plan["entities"]:
        source = entity.get("source") or {}
        if "cited" in source:
            out.append(source["cited"])
        elif entity["kind"] == "person":
            out.append(entity["name"])
    return out


def _blank(kind, prompt, cited, seconds=None, after=None):
    return {"act": ACT_RENDER, "kind": kind, "prompt": prompt, "from": cited,
            "seconds": seconds, "aspect": None, "say": "", "after": after, "replaces": None}


def _inline(description):
    """A description as it reads inside the sheet's sentence: "A man in his
    forties." is "a man in his forties". Only a leading article is lowered —
    "Anna's coat" keeps its capital — and the full stop goes."""
    text = description.rstrip(".")
    first, _, rest = text.partition(" ")
    return f"{first.lower()} {rest}" if rest and first in ("A", "An", "The") else text


def action_for(plan, row_id):
    """A row -> the chat action that renders it.

    Raises when something the row cites has not landed yet: the run never
    queues a row ahead of what it depends on, so that is a bookkeeping error
    worth a sentence, not a render without its picture.
    """
    every = rows(plan)
    row = _row(plan, row_id, every)
    handles = handles_of(plan)
    for dep in row["deps"]:
        if dep not in handles:
            raise PlanError(f"{row_id} needs {dep}, which has not rendered yet.")
    if row["kind"] == "sheet":
        entity = next(e for e in plan["entities"] if e["id"] == row["entity"])
        prompt = SHEETS[entity["kind"]].format(description=_inline(entity["description"]))
        return _blank(KIND_STILL, _with_look(prompt, plan), [])
    shot = next(s for s in plan["shots"] if s["id"] == row["shot"])
    prompt, cited = _resolve(plan, shot["action"], handles)
    if row["kind"] == "keyframe":
        return _blank(KIND_STILL, _with_look(prompt, plan), cited)
    wording = CONTINUITY.get(row["continues"])
    if wording:
        prompt = f"{prompt} {wording}"
    keyframe = f"kf.{row['id']}"
    if keyframe in row["deps"]:
        cited = [f"{handles[keyframe]}:{ROLE_START}"] + cited
    after = next((handles[d] for d in row["deps"] if d in {c["id"] for c in clips(plan)}), None)
    return _blank(KIND_VIDEO, _with_look(prompt, plan), cited, row["seconds"], after)


def change_action(plan, row_id, change):
    """A change to a rendered prep picture — a sheet or an opening frame —
    said in words -> the chat action that makes it on the room's ordinary
    edit path: the old picture cited plain, the change as the prompt, as a
    typed "make @pic-3 older" would be. The new picture is the row's new
    candidate and needs approving again (`land`).

    Names from the plan come off as plain words: the edit family is changing
    one picture, and `@keeper` in its prompt would be a citation of somebody
    the render was never sent."""
    row = _row(plan, row_id)
    if row["phase"] != PREP:
        raise PlanError(f"{row_id} is not a picture made for approval.")
    handle = handles_of(plan).get(row_id)
    if not handle:
        raise PlanError(f"{row_id} has no picture to change yet.")

    def plain(match):
        entity = _entity(plan, match.group(1))
        return entity["name"].replace("_", " ") if entity else match.group(0)

    return _blank(KIND_STILL, CITE_RE.sub(plain, _text(change, "the change")), [handle])


def prune(plan):
    """The plan less the render records of rows it no longer has.

    A replan writes new beats and shots under new ids, so the clips and
    opening frames of the old ones have no row to be stale against; their
    records would only ride along in every saved chat. A sheet's record
    stays while its entity does — a replan keeps the people and places it
    already made (`director_calls.replan`)."""
    plan = copy.deepcopy(plan)
    have = {r["id"] for r in rows(plan)}
    plan["renders"] = {rid: r for rid, r in (plan.get("renders") or {}).items() if rid in have}
    return plan


# ---- fingerprints and states ---------------------------------------------------

def fingerprint(plan, row_id, every=None, memo=None):
    """What a row renders from, hashed. Twelve hex characters.

    Its kind, family, length, prompt as the model wrote it (with the look and
    the fixed wording that will be appended), and for each row it depends on,
    the handle that row landed as — but only while that render is still
    current. A dependency with nothing landed, or whose landed render has
    gone stale, stands for its own fingerprint instead. That is what makes
    staleness flow downhill on its own: a redone sheet is a new handle is a
    new fingerprint for everything citing it, and an edited shot is stale
    while it still holds its old clip, so the clip that continues from it is
    stale too.
    """
    every = every if every is not None else rows(plan)
    memo = memo if memo is not None else {}
    if row_id in memo:
        return memo[row_id]
    row = _row(plan, row_id, every)
    rail = plan.get("rail") or {}
    handles = handles_of(plan)
    if row["kind"] == "sheet":
        entity = next(e for e in plan["entities"] if e["id"] == row["entity"])
        body = [entity["kind"], entity["description"]]
        family = rail.get("still")
    else:
        shot = next(s for s in plan["shots"] if s["id"] == row["shot"])
        # Citations by entity id, not name: renaming the keeper is not a
        # change to anything the shot shows.
        action = CITE_RE.sub(lambda m: "@" + ((_entity(plan, m.group(1)) or {}).get("id")
                                              or m.group(1)), shot["action"])
        body = [action, row.get("seconds"), row.get("continues")]
        family = rail.get("video") if row["kind"] == "clip" else rail.get("still")
    records = plan.get("renders") or {}
    deps = []
    for dep in row["deps"]:
        mark = fingerprint(plan, dep, every, memo)
        current = (records.get(dep) or {}).get("fingerprint") == mark
        deps.append(handles[dep] if dep in handles and current else mark)
    blob = json.dumps([row["kind"], family, rail.get("aspect"), plan.get("look"), body, deps],
                      ensure_ascii=False, sort_keys=True)
    memo[row_id] = hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]
    return memo[row_id]


def state_of(plan, row_id, every=None, memo=None):
    """A row's state, read off its render against its fingerprint now."""
    every = every if every is not None else rows(plan)
    record = (plan.get("renders") or {}).get(row_id)
    if not isinstance(record, dict):
        return PLANNED
    state = record.get("state")
    if state in (RENDERING, FAILED):
        return state
    if record.get("fingerprint") != fingerprint(plan, row_id, every, memo):
        return STALE
    return state if state in (PENDING, APPROVED) else PLANNED


def states(plan):
    """`{row id: state}` for every row, and for every cited entity (always
    approved: a picture the person chose is approved by being chosen)."""
    every, memo = rows(plan), {}
    out = {e["id"]: APPROVED for e in plan["entities"] if not _renders(e)}
    for row in every:
        out[row["id"]] = state_of(plan, row["id"], every, memo)
    return out


def _record(plan, row_id, **fields):
    plan = copy.deepcopy(plan)
    _row(plan, row_id)
    plan.setdefault("renders", {})[row_id] = {**(plan["renders"].get(row_id) or {}), **fields}
    return plan


def start(plan, row_id):
    """The row is queued. -> `(plan, fingerprint)`; the fingerprint goes back
    with the render to `land`, so a plan edited while it rendered lands the
    render as stale rather than as current."""
    mark = fingerprint(plan, row_id)
    return _record(plan, row_id, state=RENDERING, fingerprint=mark, error=None), mark


def land(plan, row_id, handle, mark):
    """A render finished as `handle`. A prep row waits for the person; a run
    row is done."""
    phase = _row(plan, row_id)["phase"]
    return _record(plan, row_id, state=PENDING if phase == PREP else APPROVED,
                   handle=handle, fingerprint=mark, error=None)


def fail(plan, row_id, error):
    return _record(plan, row_id, state=FAILED, error=_text(error, "the error", required=False))


def approve(plan, row_id):
    if state_of(plan, row_id) != PENDING:
        raise PlanError(f"{row_id} is not waiting for approval.")
    return _record(plan, row_id, state=APPROVED)


def can_run(plan):
    """Whether Run is enabled: every prep row approved."""
    st = states(plan)
    return all(st[r["id"]] == APPROVED for r in rows(plan) if r["phase"] == PREP)


def prep_steps(plan):
    """What *Make the missing pieces* renders now: prep rows not yet rendered
    or gone stale, whose deps are approved. Keyframes wait for the sheets
    they cite, since a keyframe of an unapproved face is wasted."""
    return _ready(plan, PREP)


def run_steps(plan):
    """Everything Run still has to render, in order: the clips not yet
    approved."""
    st = states(plan)
    return [r["id"] for r in rows(plan) if r["phase"] == RUN and st[r["id"]] != APPROVED]


def next_step(plan):
    """The one row the run renders next, or None when nothing is ready (done,
    or waiting on something rendering). Rendering is strictly one at a time:
    a pin waits for its predecessor's last frame anyway, and one GPU does
    one thing."""
    st = states(plan)
    if any(s == RENDERING for s in st.values()):
        return None
    ready = _ready(plan, RUN, st)
    return ready[0] if ready else None


def _ready(plan, phase, st=None):
    st = st if st is not None else states(plan)
    out = []
    for row in rows(plan):
        if row["phase"] != phase or st[row["id"]] in (APPROVED, PENDING, RENDERING):
            continue
        if all(st.get(d) == APPROVED for d in row["deps"]):
            out.append(row["id"])
    return out


# ---- editing -------------------------------------------------------------------

HEADER = "header"
EDITABLE = {
    "header": ("title", "seconds", "look", "keyframes", "shot_limit"),
    "b": ("text", "weight"),
    "e": ("name", "description", "source"),
    "s": ("action", "continues"),
}


def edit(plan, row_id, fields):
    """One row changed -> the new plan, validated.

    Only the authored fields of a row move, and only through their own
    readers, so a card edit and a plan turn's edit are held to the same rules
    as the call that first wrote the row. What code owns — seconds, splits,
    `after`, staleness — is recomputed from the result, never edited.
    """
    if not isinstance(fields, dict) or not fields:
        raise PlanError("an edit must name at least one field to change.")
    plan = copy.deepcopy(plan)
    prefix = HEADER if row_id == HEADER else re.sub(r"\d+$", "", str(row_id))
    allowed = EDITABLE.get(prefix)
    if allowed is None:
        raise PlanError(f"{row_id} is not a row that can be edited.")
    bad = [k for k in fields if k not in allowed]
    if bad:
        raise PlanError(f"{row_id} has no field {bad[0]!r}; it has {', '.join(allowed)}.")
    if prefix == HEADER:
        if "title" in fields:
            plan["title"] = _text(fields["title"], '"title"')[:80]
        if "seconds" in fields:
            plan["seconds"] = _whole(fields["seconds"], '"seconds"', 1, MAX_SECONDS)
        if "look" in fields:
            plan["look"] = _text(fields["look"], '"look"', required=False)
        if "keyframes" in fields:
            plan["keyframes"] = bool(fields["keyframes"])
        if "shot_limit" in fields:
            plan["shot_limit"] = _whole(fields["shot_limit"], "the shot limit", 1, MAX_SECONDS)
        return validate(plan)
    key = {"b": "beats", "e": "entities", "s": "shots"}[prefix]
    row = next((r for r in plan[key] if r["id"] == row_id), None)
    if row is None:
        raise PlanError(f"there is no row {row_id} in the plan.")
    if prefix == "b":
        row.update(_read_beat({"text": row["text"], "weight": row["weight"], **fields}, row_id))
    elif prefix == "s":
        merged = read_shots([{**{k: row[k] for k in ("action", "continues")}, **fields}], names(plan))[0]
        row.update(merged)
    else:
        _edit_entity(plan, row, fields)
    return validate(plan)


def _edit_entity(plan, row, fields):
    if "description" in fields:
        row["description"] = _text(fields["description"], f"@{row['name']}'s description")
    if "source" in fields:
        # "use @george for the keeper": the entity now reads as somebody the
        # person cast, its sheet is no longer a row, and its render record
        # goes with it. Only a person can be cast.
        cited = fields["source"]
        if cited in (None, "", "new"):
            row["source"] = {"new": True}
        else:
            name = name_of(cited)
            if not name:
                raise PlanError(f"{_shown(cited)} is not a name from the cast.")
            if row["kind"] != "person":
                raise PlanError(f"@{row['name']} is a {row['kind']}; only a person "
                                f"can be played by a cast member.")
            row["source"] = {"cited": name}
            plan["renders"].pop(row["id"], None)
    if "name" in fields:
        name = name_of(fields["name"])
        if not name:
            raise PlanError(f"{_shown(fields['name'])} is not a name an entity can have.")
        if name != row["name"] and _entity(plan, name):
            raise PlanError(f"@{name} is already in the plan.")
        old = row["name"]
        row["name"] = name
        # Every shot citing the old name cites the new one: a rename is not
        # a change to what any shot shows.
        pattern = re.compile(rf"@{re.escape(old)}\b(?!-)", re.IGNORECASE)
        for shot in plan["shots"]:
            shot["action"] = pattern.sub("@" + name, shot["action"])
