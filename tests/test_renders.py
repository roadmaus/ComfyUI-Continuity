"""Which shots a render is made of: recorded, matched once, followed, forgotten.

    python3 tests/test_renders.py
"""

import os
import sys
import tempfile
import types

import layout
from harness import check, passed

user = tempfile.mkdtemp()
sys.modules["folder_paths"] = types.SimpleNamespace(get_user_directory=lambda: user)
renders = layout.load("renders").renders

H3 = "continuity/renders/h3"
LENGTHS = {}


def row(path, mtime, seconds):
    LENGTHS[path] = seconds
    folder, _, name = path.rpartition("/")
    return {"path": path + " [output]", "name": name, "subfolder": folder, "mtime": mtime}


renders._seconds = lambda path: LENGTHS[os.path.relpath(path, "/out")]


def shots(rows):
    for entry in rows:
        entry.pop("shots", None)
    renders.annotate("/out", rows, " [output]")
    return {entry["name"]: [os.path.basename(s)[:-len(" [output]")] for s in entry["shots"]] for entry in rows if "shots" in entry}


rows = [
    row(f"{H3}/takes/H3_00001_s01.mp4", 10, 5.0), row(f"{H3}/takes/H3_00002_s02.mp4", 20, 4.0),
    row(f"{H3}/H3_00001_.mp4", 21, 9.0),
    # The first shot again, unmade: only the second was shot.
    row(f"{H3}/takes/H3_00003_s02.mp4", 30, 4.5), row(f"{H3}/H3_00002_.mp4", 31, 9.5),
    # Lengths that do not add up are not believed.
    row(f"{H3}/takes/H3_00004_s02.mp4", 40, 4.0), row(f"{H3}/H3_00003_.mp4", 41, 30.0),
    # One shot is a render of its own.
    row(f"{H3}/H3_00004_.mp4", 50, 5.0),
    row("continuity/stills/h3image/H3Image_00001_.png", 60, 0),
]
want = {"H3_00001_.mp4": ["H3_00001_s01.mp4", "H3_00002_s02.mp4"],
        "H3_00002_.mp4": ["H3_00001_s01.mp4", "H3_00003_s02.mp4"]}
check("old renders are matched, a reused shot included", shots(rows), want)
check("only shots are takes", [r["name"] for r in rows if r.get("take")],
      ["H3_00001_s01.mp4", "H3_00002_s02.mp4", "H3_00003_s02.mp4", "H3_00004_s02.mp4"])
renders._seconds = lambda path: 1 / 0
check("a matched render is not opened again", shots(rows), want)

renders.record(f"{H3}/H3_00005_.mp4", [f"{H3}/H3_00004_.mp4", f"{H3}/takes/H3_00003_s02.mp4"])
rows.append(row(f"{H3}/H3_00005_.mp4", 70, 1))
check("a recorded render is what it says", shots(rows)["H3_00005_.mp4"],
      ["H3_00004_.mp4", "H3_00003_s02.mp4"])
renders.moved(f"{H3}/H3_00004_.mp4", "keep/H3_00004_.mp4")
rows[7] = row("keep/H3_00004_.mp4", 50, 5.0)
check("a moved shot is followed", shots(rows)["H3_00005_.mp4"], ["H3_00004_.mp4", "H3_00003_s02.mp4"])
del rows[0]
check("a deleted shot leaves the list, and one shot is no list",
      shots(rows).get("H3_00001_.mp4"), None)
renders.removed(f"{H3}/H3_00005_.mp4")
check("a deleted render is forgotten", f"{H3}/H3_00005_.mp4" in renders._load(), False)
passed("a render knows its shots")
