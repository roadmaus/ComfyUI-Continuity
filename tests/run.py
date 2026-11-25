#!/usr/bin/env python3
"""Run the suites side by side and say which passed, which failed and which
did not run.

    <comfy-venv>/bin/python3 tests/run.py            every suite
    <comfy-venv>/bin/python3 tests/run.py keystone   the ones with that in their name
    <comfy-venv>/bin/python3 tests/run.py -j 4       four at a time

Every suite is a program of its own and stays one; this starts them, several
at a time, and reads how each ended. A suite that skipped is listed with its
reason and never counted as passed: a run where the graph suites found no
ComfyUI is not a run of the graph suites.

COMFYUI_PATH is set for the suites when it is not set already and this checkout
sits in a ComfyUI's `custom_nodes`. Node is looked for on the path, as the
suites look for it.
"""

import argparse
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

TESTS = os.path.dirname(os.path.abspath(__file__))
COMFY = os.path.dirname(os.path.dirname(os.path.dirname(TESTS)))

parser = argparse.ArgumentParser()
parser.add_argument("names", nargs="*", help="run the suites with any of these in their file name")
parser.add_argument("-j", "--jobs", type=int, default=min(8, os.cpu_count() or 1), help="how many run at once")
args = parser.parse_args()

env = dict(os.environ)
if "COMFYUI_PATH" not in env and os.path.isfile(os.path.join(COMFY, "folder_paths.py")):
    env["COMFYUI_PATH"] = COMFY


def emptiest_gpu():
    """The index of the card with the most memory free, or None without `nvidia-smi`."""
    try:
        free = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                              capture_output=True, text=True, check=True).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        return None
    return max(range(len(free)), key=lambda card: int(free[card])) if free else None


# Several suites at once each take a little of a card, and a card a render has
# filled has none to give: they go to the one with the most room.
card = None if "CUDA_VISIBLE_DEVICES" in env else emptiest_gpu()
if card is not None:
    env["CUDA_VISIBLE_DEVICES"] = str(card)

# The two that take half a minute start first, so the run does not end waiting on them.
LONG = ("test_screens_track.py", "test_seam_anchor.py")
suites = sorted((name for name in os.listdir(TESTS)
                 if name.startswith("test_") and name.endswith(".py")
                 and (not args.names or any(part in name for part in args.names))),
                key=lambda name: (name not in LONG, name))


def run(name):
    began = time.monotonic()
    done = subprocess.run([sys.executable, name], cwd=TESTS, env=env, text=True, errors="replace",
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return name, done.returncode, done.stdout, time.monotonic() - began


began = time.monotonic()
with ThreadPoolExecutor(args.jobs) as pool:
    results = list(pool.map(run, suites))

skipped = [(name, line) for name, code, out, _ in results
           for line in out.splitlines() if code == 0 and line.startswith("skipped: ")]
failed = [(name, out) for name, code, out, _ in results if code != 0]

for name, out in failed:
    print(f"== {name}")
    print("\n".join(out.rstrip().splitlines()[-25:]))
    print()
for name, line in skipped:
    print(f"{name}: {line}")
slow = sorted(results, key=lambda result: -result[3])[:5]
print("slowest: " + ", ".join(f"{name} {seconds:.0f} s" for name, _, _, seconds in slow))
print(f"{len(results) - len(failed) - len(skipped)} passed, {len(failed)} failed, {len(skipped)} skipped, "
      f"of {len(results)} in {time.monotonic() - began:.0f} s")
if failed:
    print("failed: " + " ".join(name for name, _ in failed))
sys.exit(1 if failed else 0)
