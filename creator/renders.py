"""Which shots a finished render was made of, for the gallery.

A piece of several shots writes a file per shot under `takes/` and then the
piece, and nothing in either says they belong together. The save node records it
here as it writes the piece; a piece written before this existed is matched once
from what is on disk and then recorded the same way.

One small JSON in the user directory, keyed by the render's path under output/.
It is a convenience for the grid and nothing else reads it: losing it costs the
grouping of renders that cannot be matched again, and no file.
"""

import json
import logging
import os
import re
import threading

import folder_paths

FILE = "continuity.renders.json"
PIECE = re.compile(r"^(?P<stem>.+)_(?P<number>\d{5})_\.mp4$")
TAKE = re.compile(r"^(?P<stem>.+)_(?P<number>\d{5})_s(?P<shot>\d{2,})\.mp4$")
# How far a piece may be from the length of its shots, in seconds.
SLACK = 0.25

_lock = threading.Lock()


def _path():
    return os.path.join(folder_paths.get_user_directory(), FILE)


def _load():
    try:
        with open(_path(), encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(data):
    path = _path()
    with open(path + ".tmp", "w", encoding="utf-8") as file:
        json.dump(data, file, indent=1)
    os.replace(path + ".tmp", path)


def is_take(relative):
    """Whether this is a shot's working file rather than a render of its own."""
    folder, _, name = relative.rpartition("/")
    return folder.rpartition("/")[2] == "takes" and bool(TAKE.match(name))


def record(render, shots):
    """Remember that `render` is `shots` in order, both relative to output/."""
    try:
        with _lock:
            data = _load()
            data[render] = list(shots)
            _save(data)
    except OSError as exc:
        # The render is on disk; the grid showing its shots apart is the cost.
        logging.warning("[Continuity] could not record the render's shots: %s", exc)


def moved(source, target):
    """A file under output/ was moved, so every mention of it moves."""
    with _lock:
        data = _load()
        after = {target if render == source else render:
                 [target if shot == source else shot for shot in shots]
                 for render, shots in data.items()}
        if after != data:
            _save(after)


def removed(path):
    with _lock:
        data = _load()
        if data.pop(path, None) is not None:
            _save(data)


def _seconds(path):
    import av

    with av.open(path) as container:
        stream = container.streams.video[0]
        if stream.frames and stream.average_rate:
            return float(stream.frames / stream.average_rate)
        return float(container.duration or 0) / av.time_base


def _match(root, piece, earlier, takes, seconds):
    """The shots of one unrecorded piece, or [].

    The takes written since the piece before it are its own. A shot it reused is
    an older file, so a missing number is filled with the latest take of that
    number, and the whole is believed only when the lengths add up to the
    piece's.
    """
    own = {}
    older = {}
    for take in takes:
        if take["mtime"] > piece["mtime"]:
            break
        shot = int(TAKE.match(take["name"])["shot"])
        older[shot] = take
        if take["mtime"] > earlier:
            own[shot] = take
    if not own:
        return []
    try:
        total = seconds(piece)
        for last in range(max(own), max(older) + 1):
            chosen = [own.get(n) or older.get(n) for n in range(1, last + 1)]
            if len(chosen) > 1 and all(chosen) and abs(
                    sum(seconds(take) for take in chosen) - total) < SLACK:
                return [take["path"] for take in chosen]
    except Exception as exc:  # noqa: BLE001 — a file that cannot be read is not matched
        logging.warning("[Continuity] could not match %s to its shots: %s", piece["path"], exc)
    return []


def _backfill(root, rows, data):
    """Match the pieces in the listing nothing was recorded for. -> changed."""
    pieces, takes = {}, {}
    for row in rows:
        hit = PIECE.match(row["name"])
        if hit:
            pieces.setdefault((row["subfolder"], hit["stem"]), []).append(row)
            continue
        if is_take(row["path"]):
            folder = row["subfolder"].rpartition("/")[0]
            takes.setdefault((folder, TAKE.match(row["name"])["stem"]), []).append(row)
    lengths = {}

    def seconds(row):
        if row["path"] not in lengths:
            lengths[row["path"]] = _seconds(os.path.join(root, row["path"]))
        return lengths[row["path"]]

    changed = False
    for key, shelf in pieces.items():
        mine = sorted(takes.get(key, []), key=lambda row: row["mtime"])
        if not mine:
            continue
        earlier = 0
        for piece in sorted(shelf, key=lambda row: row["mtime"]):
            if piece["path"] not in data:
                data[piece["path"]] = _match(root, piece, earlier, mine, seconds)
                changed = True
            earlier = piece["mtime"]
    return changed


def annotate(root, rows, annotation):
    """Put `shots` on every listed render made of several, and `take` on a shot."""
    bare = [{**row, "path": row["path"][:len(row["path"]) - len(annotation)]} for row in rows]
    with _lock:
        data = _load()
        if _backfill(root, bare, data):
            try:
                _save(data)
            except OSError as exc:
                logging.warning("[Continuity] could not record the renders' shots: %s", exc)
    there = {row["path"] for row in bare}
    for row, plain in zip(rows, bare):
        if is_take(plain["path"]):
            row["take"] = True
        shots = [shot for shot in data.get(plain["path"], []) if shot in there]
        if len(shots) > 1:
            row["shots"] = [shot + annotation for shot in shots]
