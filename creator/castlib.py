"""The cast library, read without a browser: who is kept, and one of them walked into a piece.

The library is the frontend's (`web/creator/presets.js`): an index file with a
row per preset and a body file per row, both in ComfyUI's userdata, and a kept
member is a preset of scope `cast` whose body is them with their files named
rather than handled. On a node, *From the library* reads that body and
`presets.addSubjectToPiece` lands them: their files attach, handles are issued,
and the subject is written against those handles.

A render asked for by a script (`routes/render.py`) has no page to do that in,
so a prompt that says `@anna` there cited nobody. This module is the same
landing, in Python, onto the piece the route builds: `land` is
`addSubjectToPiece` with `pool: true`, the way the chat room casts — the files
go on the piece's shelf as `ref-N`, since a script's own files are the
ledger's (`pic-N`) and the two lists must not share a counter.

Pure: no ComfyUI, no disk. The route reads the two files and hands them in.
"""

import re

from . import compile as core
from .families.h3 import subjects

SCOPE = "cast"
# The four slots a file can sit in behind a subject. Mirrors
# `presets.SUBJECT_SLOTS`; the three that hold several files, `cast.LIST_ROLES`.
SLOTS = ("from", "motion", "voice", "replaces")
LIST_SLOTS = ("from", "motion", "replaces")
SUBJECT_TAKES = ("person", "object", "scene", "style")
# A name written after an `@`: no hyphen, which is what tells it from a file's
# handle (`subjects.HANDLE_RE`).
_NAME = re.compile(r"(?<![\w@])@([A-Za-z][A-Za-z0-9_]{0,31})(?![\w-])")


def roster(index):
    """The index file's kept members, newest first -> `[row]`.

    A row is the library's own (`id`, `name`, `facts`, `updated`). Shipped rows
    carry no body file and nobody ships a person, so they are left out.
    """
    rows = (index or {}).get("presets") if isinstance(index, dict) else None
    kept = [row for row in rows or []
            if isinstance(row, dict) and row.get("scope") == SCOPE and not row.get("builtin")
            and isinstance(row.get("id"), str) and str(row.get("name") or "").strip()]
    return sorted(kept, key=lambda row: row.get("updated") or 0, reverse=True)


def member(body):
    """A body file's member, or None where it holds nobody."""
    data = (body or {}).get("data") if isinstance(body, dict) else None
    stored = (data or {}).get("cast") if isinstance(data, dict) else None
    return stored if isinstance(stored, dict) else None


def cited(prompt, rows):
    """The kept members a prompt names, in the order it names them -> `[row]`.

    In any case, as `chat.validate` accepts a name in any case; the newest of
    two rows with one name, which is the one the library shows first.
    """
    by_name = {}
    for row in rows:
        by_name.setdefault(str(row["name"]).strip().lower(), row)
    out = []
    for word in _NAME.findall(prompt or ""):
        row = by_name.get(word.lower())
        if row is not None and row not in out:
            out.append(row)
    return out


def summary(row, stored=None):
    """One member as a listing says them: name, what they are, what is behind them."""
    facts = row.get("facts") if isinstance(row.get("facts"), dict) else {}
    stored = stored or {}
    wears = stored.get("wears") if isinstance(stored.get("wears"), dict) else {}
    return {
        "name": str(row["name"]).strip(),
        "takes": stored.get("takes") or facts.get("takes") or "person",
        "description": str(stored.get("description") or ""),
        "pictures": sum(1 for f in stored.get("files") or []
                        if isinstance(f, dict) and (f.get("kind") or "image") == "image"),
        "voice": any(isinstance(f, dict) and f.get("slot") == "voice"
                     for f in stored.get("files") or []),
        # The families they wear a LoRA on, which is where they are most themselves.
        "loras": sorted(family for family, entry in wears.items()
                        if isinstance(entry, dict) and entry.get("loras")),
    }


def _scope_kind(asset):
    return "audio" if asset.get("kind") == "audio" or asset.get("track") == "sound" \
        else asset.get("kind")


def _take_options(asset):
    return core.TAKES.get(_scope_kind(asset), ()) if asset.get("role") == "reference" else ()


def _slot_take(takes, slot, asset):
    wanted = {"from": takes, "motion": "motion", "voice": "voice", "replaces": "edit"}.get(slot)
    return wanted if wanted in _take_options(asset) else None


def _inherit_take(takes, slot, asset):
    """Narrow a file to what its slot says, unless it is narrowed already.
    `state.inheritTake`."""
    wanted = _slot_take(takes, slot, asset)
    if not wanted:
        return
    standing = asset.get("takes") if asset.get("takes") in _take_options(asset) else "full"
    if standing == "full":
        asset["takes"] = wanted


def _taken(piece):
    taken = set()
    for asset in piece.get("assets") or []:
        taken.add(asset.get("handle"))
        taken.update(panel.get("handle") for panel in asset.get("panels") or [])
    return taken


def _next(taken, prefix="ref"):
    n = 1
    while f"{prefix}-{n}" in taken:
        n += 1
    taken.add(f"{prefix}-{n}")
    return f"{prefix}-{n}"


def _plate(file, taken):
    """A file the library holds as a cutout or a sheet, as the plate it is.
    `state.plateEntry` with the pool's prefixes."""
    entry = {"handle": _next(taken), "kind": "image", "role": "reference",
             "filename": file["filename"], "ref_size": file.get("ref_size") or "max",
             "panels": []}
    for source in file["panels"]:
        if not isinstance(source, dict) or not source.get("path"):
            continue
        panel = {"handle": _next(taken), "filename": source["path"]}
        if source.get("cut"):
            panel["cut"] = True
        for key in ("rect", "points", "crop", "takes"):
            if source.get(key):
                panel[key] = source[key]
        entry["panels"].append(panel)
    return entry


def _features(stored):
    """`state.subjectFeatures`: rows with something in them."""
    out = []
    for item in stored.get("features") or []:
        if isinstance(item, str):
            row = {"is": item.strip(), "instead": ""}
        elif isinstance(item, dict):
            row = {"is": str(item.get("is") or "").strip(),
                   "instead": str(item.get("instead") or "").strip()}
            if item.get("attr"):
                row["attr"] = str(item["attr"]).strip()
        else:
            continue
        if row["is"] or row.get("attr"):
            out.append(row)
    return out


def land(stored, piece):
    """Walk one kept member into `piece`, files and all -> their subject.

    `presets.addSubjectToPiece(stored, piece, {pool: true})`. A file the shelf
    already holds is used rather than attached twice, and a name the piece
    already has is kept apart (`anna_2`), as on the node.
    """
    assets = piece.setdefault("assets", [])
    cast = piece.setdefault("subjects", [])
    takes = stored.get("takes") if stored.get("takes") in SUBJECT_TAKES else "person"
    taken = _taken(piece)
    slots = {"from": [], "motion": [], "replaces": []}
    notes, triggers = {}, {}
    for file in stored.get("files") or []:
        if not isinstance(file, dict) or not file.get("filename"):
            continue
        kind = file.get("kind") or "image"
        asset = next((a for a in assets
                      if a.get("filename") == file["filename"] and a.get("kind") == kind), None)
        if asset is None:
            if file.get("panels"):
                asset = _plate(file, taken)
            else:
                asset = {"handle": _next(taken), "kind": kind, "role": "reference",
                         "filename": file["filename"],
                         "ref_size": file.get("ref_size") or "max"}
                for key in ("track", "trim"):
                    if file.get(key):
                        asset[key] = file[key]
                if isinstance(file.get("mods"), dict) and file["mods"]:
                    asset["mods"] = dict(file["mods"])
            assets.append(asset)
        else:
            if file.get("ref_size") and asset.get("role") == "reference":
                asset["ref_size"] = file["ref_size"]
            if isinstance(file.get("mods"), dict) and asset.get("role") == "reference" \
                    and not asset.get("panels"):
                asset["mods"] = {**(asset.get("mods") or {}), **file["mods"]}
        handle = asset["handle"]
        if file.get("note"):
            notes[handle] = str(file["note"])
        if file.get("trigger"):
            triggers[handle] = str(file["trigger"])
        slot = file.get("slot")
        if slot in LIST_SLOTS:
            slots[slot].append(handle)
        elif slot in SLOTS:
            slots[slot] = handle
        _inherit_take(takes, slot, asset)
        panels = asset.get("panels") or []
        if asset.get("takes") and len(panels) == 1 and not panels[0].get("takes"):
            panels[0]["takes"] = asset["takes"]

    names = {str(s.get("handle") or "").lower() for s in cast if isinstance(s, dict)}
    base = str(stored.get("handle") or "subject")
    if not subjects.HANDLE_RE.match(base):
        base = "subject"
    name, n = base, 2
    while name.lower() in names:
        name, n = f"{base}_{n}", n + 1

    subject = {"handle": name, "takes": takes, "from": slots["from"]}
    if slots["motion"]:
        subject["motion"] = slots["motion"]
    if slots.get("voice"):
        subject["voice"] = slots["voice"]
    if slots["replaces"]:
        subject["replaces"] = slots["replaces"]
    if stored.get("description"):
        subject["description"] = str(stored["description"])
    features = _features(stored)
    if stored.get("replaces_what"):
        subject["replaces_what"] = str(stored["replaces_what"])
    if stored.get("relationship") in subjects.MARKERS:
        subject["relationship"] = stored["relationship"]
    if notes:
        subject["notes"] = notes
    if triggers:
        subject["triggers"] = triggers
    # What they wear, by family, as the blob stores it; a member kept before
    # the rows existed carries a flat list, which `chat.cast_entries` and
    # `subjects.parse` both still read.
    if isinstance(stored.get("wears"), dict) and stored["wears"]:
        subject["wears"] = {str(family): dict(entry) for family, entry in stored["wears"].items()
                            if isinstance(entry, dict)}
    elif isinstance(stored.get("loras"), list) and stored["loras"]:
        subject["loras"] = list(stored["loras"])
    # `state.seedSubject`: the baseline rows in front, once.
    if not stored.get("seeded"):
        attributes = [key for key, _ in subjects.ATTRIBUTES.get(takes, subjects.ATTRIBUTES["person"])[1]]
        features = [{"attr": attr, "is": "", "instead": ""} for attr in attributes] + features
    if features:
        subject["features"] = features
    subject["seeded"] = True
    cast.append(subject)
    return subject
