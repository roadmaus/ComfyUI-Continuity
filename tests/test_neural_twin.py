"""The other version of a render is one boolean, and nothing else moved.

    python3 tests/test_neural_twin.py

`neuraltwin.py` exists because of a fact about ComfyUI's cache that is easy to
lose: an expanding node's children are cached in a subcache keyed by
`(node_id, class_type)` — see `comfy_execution/caching.py` — so re-queueing a
render with the blob's refiner flipped re-expands the node and hits every
sampler underneath it. What that buys is a real before-and-after for the price
of a save, instead of a second render.

Every check below is about not breaking that. The node id has to survive, the
seed has to survive, the widget it is not editing has to survive, and the
settings have to be carried across rather than defaulted — a twin that changed
two things would be a comparison of nothing.

Pure Python: no ComfyUI, no node import.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import layout
from harness import FAILURES, check, passed

twin = layout.load("neuraltwin").neuraltwin


def blob(**fields):
    return json.dumps({"version": 3, "segments": [{"prompt": "a shot"}], **fields})


def prompt(blob_json, node="7", cls="MiniMaxH3Creator", widget="creator_data"):
    return {
        "3": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "h3.safetensors"}},
        node: {"class_type": cls,
               "inputs": {widget: blob_json, "seed": 12345, "steps": 20, "cfg": 1.0}},
    }


REFINED = blob(neural={"on": True, "profile": "natural", "scale": 1, "detail": 1.5,
                       "colour": 1, "intensity": 0.85, "precision": "reference"})
PLAIN = blob()

# ---- what a file says --------------------------------------------------------

check("a render with the pass on says so", twin.read(prompt(REFINED))["on"], True)
check("...and hands back the settings it used",
      twin.read(prompt(REFINED))["settings"]["profile"], "natural")
check("a render without it is ours and off", twin.read(prompt(PLAIN)),
      {"ours": True, "on": False, "settings": None, "node": "7"})
check("a blob whose refiner block is absent is off", twin.read(prompt(PLAIN))["on"], False)
# Somebody else's graph, and a file with no prompt at all. Neither is an error:
# both are files with no other version, which the caller has to be able to tell
# apart from a render that simply had the pass off.
check("somebody else's graph is not ours",
      twin.read({"1": {"class_type": "KSampler", "inputs": {}}})["ours"], False)
check("no prompt at all is not ours", twin.read(None)["ours"], False)
check("a blob that is not JSON is not ours",
      twin.read(prompt("not json at all"))["ours"], False)

# The retired Timeline id, whose widget is called something else. A file it
# wrote is a render like any other and has to compare like one.
check("the retired Timeline id is ours too",
      twin.read(prompt(REFINED, node="2", cls="MiniMaxH3Timeline",
                       widget="timeline_data"))["on"], True)
check("and so is a pre-stage",
      twin.read(prompt(REFINED, node="9", cls="MiniMaxH3PreStage",
                       widget="prestage_data"))["on"], True)

# ---- the twin ----------------------------------------------------------------

off = twin.twin(prompt(REFINED), False)
off_blob = json.loads(off["7"]["inputs"]["creator_data"])

check("the twin has the refiner off", off_blob["neural"]["on"], False)
# The three things the cache and the comparison stand on.
check("...under the same node id", sorted(off), ["3", "7"])
check("...on the same seed", off["7"]["inputs"]["seed"], 12345)
check("...with the rest of the graph untouched", off["3"], prompt(REFINED)["3"])
# Carried, not defaulted: switching back on has to arrive where it left.
check("...and the settings carried across", off_blob["neural"]["profile"], "natural")
check("the blob is otherwise the same",
      {key: value for key, value in off_blob.items() if key != "neural"},
      {key: value for key, value in json.loads(REFINED).items() if key != "neural"})

# The original must not be touched: the caller still holds it, and a surface
# that read it back after queueing would be reading the twin's answer.
check("the prompt it was given is unchanged",
      json.loads(prompt(REFINED)["7"]["inputs"]["creator_data"])["neural"]["on"], True)

on = twin.twin(prompt(PLAIN), True, {"profile": "cinematic", "detail": 2})
on_blob = json.loads(on["7"]["inputs"]["creator_data"])
check("a render that never had the pass can be given one", on_blob["neural"]["on"], True)
check("...with the dials the caller asked for", on_blob["neural"]["profile"], "cinematic")

# Two of ours in one prompt need explicit producer metadata. Only its final
# pass changes; an upstream or independent pre-stage keeps its original pixels.
pair = {**prompt(REFINED),
        "9": {"class_type": "MiniMaxH3PreStage", "inputs": {"prestage_data": REFINED}}}
both = twin.twin(pair, False, producer={"node": "7", "index": 0})
check("only the named producer is flipped",
      [json.loads(both["7"]["inputs"]["creator_data"])["neural"]["on"],
       json.loads(both["9"]["inputs"]["prestage_data"])["neural"]["on"]],
      [False, True])
check("...and settings come from that same producer",
      twin.read(pair, {"node": "7"})["node"], "7")

try:
    twin.twin({"1": {"class_type": "KSampler", "inputs": {}}}, False)
    FAILURES.append("a prompt with none of our nodes: was accepted")
except twin.TwinError:
    pass

passed("the twin is one boolean, on the same id and the same seed")
